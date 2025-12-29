defmodule FrontendWeb.ChatLive do
  use FrontendWeb, :live_view
  require Logger

  @backend_url "http://localhost:8000"

  def mount(_params, _session, socket) do
    if connected?(socket) do
      {:ok, sessions} = fetch_sessions()

      socket =
        socket
        |> assign(:sessions, sessions)
        |> assign(:current_session_id, nil)
        |> assign(:messages, [])
        |> assign(:message_input, "")
        |> assign(:loading, false)
        |> assign(:show_sidebar, true)
        |> assign(:show_debug_modal, false)
        |> assign(:debug_data, nil)
        |> assign(:deleting_session_id, nil)
        |> assign(:renaming_session_id, nil)
        |> assign(:rename_input, "")
        |> assign(:show_upload_modal, false)
        |> assign(:uploading, false)
        |> assign(:upload_progress, [])
        |> allow_upload(:documents,
          accept: ~w(.pdf .md .txt),
          max_entries: 10,
          max_file_size: 10_000_000
        )

      {:ok, socket}
    else
      {:ok,
       assign(socket,
         sessions: [],
         current_session_id: nil,
         messages: [],
         message_input: "",
         loading: false,
         show_sidebar: true,
         show_debug_modal: false,
         debug_data: nil,
         deleting_session_id: nil,
         renaming_session_id: nil,
         rename_input: "",
         show_upload_modal: false,
         uploading: false,
         upload_progress: []
       )}
    end
  end

  def handle_event("new_conversation", _params, socket) do
    session_id = UUID.uuid4()

    {:noreply,
     socket
     |> assign(:current_session_id, session_id)
     |> assign(:messages, [])
     |> push_event("focus-input", %{})}
  end

  def handle_event("select_session", %{"session_id" => session_id}, socket) do
    {:ok, messages} = fetch_messages(session_id)

    {:noreply,
     socket
     |> assign(:current_session_id, session_id)
     |> assign(:messages, messages)}
  end

  def handle_event("toggle_sidebar", _params, socket) do
    {:noreply, assign(socket, :show_sidebar, !socket.assigns.show_sidebar)}
  end

  def handle_event("toggle_debug_modal", _params, socket) do
    {:noreply, assign(socket, :show_debug_modal, !socket.assigns.show_debug_modal)}
  end

  def handle_event("open_upload_modal", _params, socket) do
    {:noreply, assign(socket, :show_upload_modal, true)}
  end

  def handle_event("close_upload_modal", _params, socket) do
    {:noreply,
     socket
     |> assign(:show_upload_modal, false)
     |> assign(:upload_progress, [])}
  end

  def handle_event("validate_upload", _params, socket) do
    {:noreply, socket}
  end

  def handle_event("submit_upload", _params, socket) do
    Logger.info("[UPLOAD] submit_upload event received")
    
    # Initialize progress tracking for each file
    files_to_upload =
      socket.assigns.uploads.documents.entries
      |> Enum.map(fn entry ->
        %{
          ref: entry.ref,
          filename: entry.client_name,
          status: :uploading,
          message: "Uploading...",
          chunks: nil,
          doc_id: nil
        }
      end)

    Logger.info("[UPLOAD] Files to upload: #{inspect(Enum.map(files_to_upload, & &1.filename))}")

    socket =
      socket
      |> assign(:uploading, true)
      |> assign(:upload_progress, files_to_upload)

    # Start async upload process
    Logger.info("[UPLOAD] Sending :process_uploads message to self()")
    send(self(), :process_uploads)

    {:noreply, socket}
  end

  def handle_event("start_rename", %{"session_id" => session_id}, socket) do
    # Find current display name
    session = Enum.find(socket.assigns.sessions, fn s -> s["session_id"] == session_id end)
    current_name = session["display_name"] || ""
    
    {:noreply,
     socket
     |> assign(:renaming_session_id, session_id)
     |> assign(:rename_input, current_name)}
  end

  def handle_event("cancel_rename", _params, socket) do
    {:noreply,
     socket
     |> assign(:renaming_session_id, nil)
     |> assign(:rename_input, "")}
  end

  def handle_event("save_rename", %{"session_id" => session_id, "display_name" => display_name}, socket) do
    # Send async rename to backend
    Task.start(fn ->
      rename_session(session_id, String.trim(display_name))
    end)
    
    # Optimistically update UI
    updated_sessions =
      Enum.map(socket.assigns.sessions, fn s ->
        if s["session_id"] == session_id do
          Map.put(s, "display_name", String.trim(display_name))
        else
          s
        end
      end)
    
    {:noreply,
     socket
     |> assign(:sessions, updated_sessions)
     |> assign(:renaming_session_id, nil)
     |> assign(:rename_input, "")}
  end

  def handle_event("delete_session", %{"session_id" => session_id}, socket) do
    # Optimistically remove from UI and mark as deleting
    filtered_sessions = Enum.filter(socket.assigns.sessions, fn s -> s["session_id"] != session_id end)
    
    socket =
      socket
      |> assign(:sessions, filtered_sessions)
      |> assign(:deleting_session_id, session_id)
    
    # If deleted session was current, clear it
    socket =
      if socket.assigns.current_session_id == session_id do
        socket
        |> assign(:current_session_id, nil)
        |> assign(:messages, [])
      else
        socket
      end
    
    # Send async delete to backend
    send(self(), {:delete_session_async, session_id})
    
    {:noreply, socket}
  end

  def handle_event("send_message", %{"message" => message}, socket) do
    message = String.trim(message)

    if message != "" and socket.assigns.current_session_id do
      # Add user message immediately
      user_msg = %{"role" => "user", "content" => message, "timestamp" => DateTime.utc_now()}
      messages = socket.assigns.messages ++ [user_msg]

      socket =
        socket
        |> assign(:messages, messages)
        |> assign(:message_input, "")
        |> assign(:loading, true)

      # Send to backend
      send(self(), {:send_to_backend, socket.assigns.current_session_id, message})

      {:noreply, socket}
    else
      {:noreply, socket}
    end
  end

  def handle_info(:process_uploads, socket) do
    Logger.info("[UPLOAD] handle_info :process_uploads called")
    Logger.info("[UPLOAD] Number of entries: #{length(socket.assigns.uploads.documents.entries)}")
    
    # Process each uploaded file
    uploaded_files =
      consume_uploaded_entries(socket, :documents, fn %{path: path}, entry ->
        Logger.info("[UPLOAD] Processing file: #{entry.client_name} from #{path}")
        
        # Send upload to backend (removed intermediate status update to avoid race condition)
        Logger.info("[UPLOAD] Calling upload_document...")
        result = upload_document(path, entry.client_name)
        Logger.info("[UPLOAD] Result: #{inspect(result)}")
        
        # Return in correct format for consume_uploaded_entries
        {:ok, {entry.ref, entry.client_name, result}}
      end)
    
    Logger.info("[UPLOAD] Uploaded files: #{inspect(uploaded_files)}")

    # Update final progress
    progress =
      Enum.map(uploaded_files, fn {ref, filename, result} ->
        case result do
          {:ok, response} ->
            %{
              ref: ref,
              filename: filename,
              status: :success,
              message: response["message"] || "Upload complete",
              chunks: response["total_chunks"],
              doc_id: response["doc_id"]
            }

          {:error, reason} ->
            %{
              ref: ref,
              filename: filename,
              status: :error,
              message: "Upload failed: #{format_error(reason)}",
              chunks: nil,
              doc_id: nil
            }
        end
      end)

    success_count = Enum.count(progress, fn p -> p.status == :success end)

    Logger.info("[UPLOAD] Progress: #{inspect(progress)}")
    Logger.info("[UPLOAD] Setting uploading=false and updating upload_progress")

    result = {:noreply,
     socket
     |> assign(:uploading, false)
     |> assign(:upload_progress, progress)
     |> put_flash(:info, "Successfully uploaded #{success_count}/#{length(progress)} document(s)")}
    
    Logger.info("[UPLOAD] Returning from handle_info")
    result
  end

  def handle_info({:upload_status, ref, status, message}, socket) do
    # Update progress for specific file
    updated_progress =
      Enum.map(socket.assigns.upload_progress, fn progress ->
        if progress.ref == ref do
          %{progress | status: status, message: message}
        else
          progress
        end
      end)

    {:noreply, assign(socket, :upload_progress, updated_progress)}
  end

  def handle_info({:delete_session_async, session_id}, socket) do
    # Fire and forget - don't wait for backend response
    Task.start(fn ->
      case delete_session(session_id) do
        {:ok, _} -> :ok
        {:error, reason} -> Logger.error("Failed to delete session: #{inspect(reason)}")
      end
    end)
    
    # Immediately clear the deleting state
    {:noreply, assign(socket, :deleting_session_id, nil)}
  end

  def handle_info({:send_to_backend, session_id, message}, socket) do
    case send_message(session_id, message) do
      {:ok, body} ->
        response_text = body["message"]
        assistant_msg = %{
          "role" => "assistant",
          "content" => response_text,
          "timestamp" => DateTime.utc_now()
        }

        messages = socket.assigns.messages ++ [assistant_msg]

        # Refresh sessions to update last_message_at
        {:ok, sessions} = fetch_sessions()

        {:noreply,
         socket
         |> assign(:messages, messages)
         |> assign(:sessions, sessions)
         |> assign(:debug_data, body["debug"])
         |> assign(:loading, false)}

      {:error, {:timeout, _e}} ->
        Logger.error("Failed to send message: transport timeout")
        {:noreply,
         socket
         |> assign(:loading, false)
         |> put_flash(:error, "Request timed out. The model may be slow right now—please try again.")}

      {:error, reason} ->
        Logger.error("Failed to send message: #{inspect(reason)}")
        {:noreply,
         socket
         |> assign(:loading, false)
         |> put_flash(:error, "Failed to send message. Please try again.")}
    end
  end

  defp fetch_sessions do
    case Req.get("#{@backend_url}/chat/sessions") do
      {:ok, %{status: 200, body: sessions}} ->
        # Sort by last_message_at desc (handle nil and string timestamps)
        sorted =
          sessions
          |> Enum.sort_by(
            fn session ->
              case session["last_message_at"] do
                nil -> ~U[1970-01-01 00:00:00Z]
                ts when is_binary(ts) ->
                  case DateTime.from_iso8601(ts) do
                    {:ok, dt, _} -> dt
                    _ -> ~U[1970-01-01 00:00:00Z]
                  end
                ts -> ts
              end
            end,
            :desc
          )

        {:ok, sorted}

      _ ->
        {:ok, []}
    end
  end

  defp fetch_messages(session_id) do
    case Req.get("#{@backend_url}/chat/sessions/#{session_id}/messages") do
      {:ok, %{status: 200, body: %{"messages" => messages}}} ->
        {:ok, messages}

      _ ->
        {:ok, []}
    end
  end

  defp send_message(session_id, message) do
    case Req.post(
           "#{@backend_url}/chat/message?debug=true",
           json: %{session_id: session_id, message: message},
           # Grok-4 can take longer than default timeouts; bump client-side timeouts
           receive_timeout: 120_000,
           connect_options: [timeout: 10_000]
         ) do
      {:ok, %{status: 200, body: body}} ->
        {:ok, body}

      {:ok, %{status: status, body: body}} ->
        {:error, {:http_error, status, body}}

      {:error, %Req.TransportError{reason: :timeout} = e} ->
        {:error, {:timeout, e}}

      error ->
        {:error, error}
    end
  end

  defp delete_session(session_id) do
    case Req.post("#{@backend_url}/chat/clear",
           json: %{session_id: session_id}
         ) do
      {:ok, %{status: 200}} ->
        {:ok, :deleted}

      error ->
        {:error, error}
    end
  end

  defp rename_session(session_id, display_name) do
    case Req.post("#{@backend_url}/chat/sessions/#{session_id}/rename?display_name=#{URI.encode(display_name)}") do
      {:ok, %{status: 200}} ->
        {:ok, :renamed}

      error ->
        {:error, error}
    end
  end

  defp upload_document(file_path, filename) do
    # Read file content
    case File.read(file_path) do
      {:ok, file_content} ->
        # Create multipart form data using iolist to handle binary data properly
        boundary = "----WebKitFormBoundary#{:rand.uniform(1_000_000_000)}"
        
        # Use iolist to avoid encoding issues with binary PDF data
        body_parts = [
          "--", boundary, "\r\n",
          "Content-Disposition: form-data; name=\"file\"; filename=\"", filename, "\"\r\n",
          "Content-Type: application/octet-stream\r\n\r\n",
          file_content,
          "\r\n--", boundary, "--\r\n"
        ]
        
        body = IO.iodata_to_binary(body_parts)
        
        case Req.post(
               "#{@backend_url}/ingest/upload",
               body: body,
               headers: [{"content-type", "multipart/form-data; boundary=#{boundary}"}]
             ) do
          {:ok, %{status: 200, body: response_body}} ->
            {:ok, response_body}

          {:ok, %{status: status, body: response_body}} ->
            {:error, {:http_error, status, response_body}}

          error ->
            {:error, error}
        end
        
      {:error, reason} ->
        {:error, {:file_read_error, reason}}
    end
  end

  def render(assigns) do
    ~H"""
    <div class="flex h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900">
      <%!-- Sidebar --%>
      <div class={[
        "transition-all duration-300 flex-shrink-0 border-r border-slate-700/50",
        @show_sidebar && "w-80",
        !@show_sidebar && "w-0"
      ]}>
        <div class={["h-full bg-slate-900/50 backdrop-blur-sm flex flex-col", !@show_sidebar && "hidden"]}>
          <%!-- Sidebar Header --%>
          <div class="p-4 border-b border-slate-700/50">
            <h2 class="text-lg font-semibold text-slate-200 mb-3">Conversations</h2>
            <div class="space-y-2">
              <button
                phx-click="new_conversation"
                class="w-full px-4 py-2.5 bg-gradient-to-r from-blue-600 to-blue-500 hover:from-blue-500 hover:to-blue-400 text-white rounded-lg font-medium transition-all duration-200 shadow-lg shadow-blue-500/20 hover:shadow-blue-500/40"
              >
                <.icon name="hero-plus" class="w-5 h-5 inline mr-2" /> New Chat
              </button>
              <button
                phx-click="open_upload_modal"
                class="w-full px-4 py-2.5 bg-gradient-to-r from-purple-600 to-purple-500 hover:from-purple-500 hover:to-purple-400 text-white rounded-lg font-medium transition-all duration-200 shadow-lg shadow-purple-500/20 hover:shadow-purple-500/40"
              >
                <.icon name="hero-arrow-up-tray" class="w-5 h-5 inline mr-2" /> Upload Documents
              </button>
            </div>
          </div>

          <%!-- Session List --%>
          <div class="flex-1 overflow-y-auto p-3 space-y-2">
            <%= if @sessions == [] do %>
              <p class="text-slate-500 text-sm text-center py-8">No conversations yet</p>
            <% else %>
              <%= for session <- @sessions do %>
                <div class={[
                  "relative group rounded-lg transition-all duration-200",
                  @current_session_id == session["session_id"] &&
                    "bg-blue-600/20 border border-blue-500/50",
                  @current_session_id != session["session_id"] &&
                    "bg-slate-800/50 hover:bg-slate-700/50 border border-transparent"
                ]}>
                  <%= if @renaming_session_id == session["session_id"] do %>
                    <%!-- Rename Mode --%>
                    <div class="px-4 py-3">
                      <form phx-submit="save_rename" phx-value-session_id={session["session_id"]}>
                        <input
                          type="text"
                          name="display_name"
                          value={@rename_input}
                          placeholder="Enter name..."
                          class="w-full px-2 py-1 bg-slate-700 border border-slate-600 rounded text-slate-200 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
                          autofocus
                        />
                        <div class="flex gap-2 mt-2">
                          <button
                            type="submit"
                            class="flex-1 px-2 py-1 bg-blue-600 hover:bg-blue-500 text-white text-xs rounded transition-colors"
                          >
                            Save
                          </button>
                          <button
                            type="button"
                            phx-click="cancel_rename"
                            class="flex-1 px-2 py-1 bg-slate-700 hover:bg-slate-600 text-slate-300 text-xs rounded transition-colors"
                          >
                            Cancel
                          </button>
                        </div>
                      </form>
                    </div>
                  <% else %>
                    <%!-- Normal Mode --%>
                    <button
                      phx-click="select_session"
                      phx-value-session_id={session["session_id"]}
                      class="w-full text-left px-4 py-3"
                    >
                      <div class="flex items-start justify-between">
                        <div class="flex-1 min-w-0 pr-2">
                          <p class="text-slate-200 font-medium text-sm truncate">
                            <%= if session["display_name"] do %>
                              {session["display_name"]}
                            <% else %>
                              Session <%= String.slice(session["session_id"], 0..7) %>
                            <% end %>
                          </p>
                          <%= if session["message_count"] do %>
                            <p class="text-slate-500 text-xs mt-1">
                              {session["message_count"]} messages
                            </p>
                          <% end %>
                        </div>
                        <%= if session["last_message_at"] do %>
                          <span class="text-xs text-slate-500">
                            {format_time(session["last_message_at"])}
                          </span>
                        <% end %>
                      </div>
                    </button>
                    <div class="absolute right-2 top-2 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                      <button
                        phx-click="start_rename"
                        phx-value-session_id={session["session_id"]}
                        class="p-1.5 bg-blue-600/10 hover:bg-blue-600/20 text-blue-400 rounded"
                        title="Rename conversation"
                      >
                        <.icon name="hero-pencil" class="w-4 h-4" />
                      </button>
                      <button
                        phx-click="delete_session"
                        phx-value-session_id={session["session_id"]}
                        class="p-1.5 bg-red-600/10 hover:bg-red-600/20 text-red-400 rounded"
                        title="Delete conversation"
                      >
                        <.icon name="hero-trash" class="w-4 h-4" />
                      </button>
                    </div>
                  <% end %>
                </div>
              <% end %>
            <% end %>
          </div>
        </div>
      </div>

      <%!-- Main Chat Area --%>
      <div class="flex-1 flex flex-col min-w-0">
        <%!-- Chat Header --%>
        <div class="p-4 border-b border-slate-700/50 bg-slate-900/50 backdrop-blur-sm flex items-center justify-between">
          <div class="flex items-center">
            <button
              phx-click="toggle_sidebar"
              class="p-2 hover:bg-slate-700/50 rounded-lg transition-colors mr-3"
            >
              <.icon name={@show_sidebar && "hero-bars-3" || "hero-bars-3"} class="w-6 h-6 text-slate-400" />
            </button>
            <h1 class="text-xl font-semibold text-slate-200">
              <%= if @current_session_id do %>
                Chat Session
              <% else %>
                ScyllaDB RAG Demo
              <% end %>
            </h1>
          </div>
          <div class="flex items-center gap-3">
            <%= if @debug_data do %>
              <button
                phx-click="toggle_debug_modal"
                class="px-3 py-1.5 bg-purple-600/20 hover:bg-purple-600/30 text-purple-400 border border-purple-500/50 rounded-lg text-sm font-medium transition-all duration-200"
              >
                <.icon name="hero-code-bracket" class="w-4 h-4 inline mr-1.5" />
                View Context
              </button>
            <% end %>
            <%= if @current_session_id do %>
              <span class="text-xs text-slate-500 font-mono">
                {String.slice(@current_session_id, 0..7)}
              </span>
            <% end %>
          </div>
        </div>

        <%!-- Messages Area --%>
        <div class="flex-1 overflow-y-auto p-6 space-y-6" id="messages-container" phx-hook=".ScrollToBottom">
          <%= if @current_session_id == nil do %>
            <div class="h-full flex items-center justify-center">
              <div class="text-center max-w-md">
                <div class="mb-6">
                  <div class="w-20 h-20 mx-auto bg-gradient-to-br from-blue-500 to-purple-600 rounded-2xl flex items-center justify-center shadow-2xl">
                    <.icon name="hero-chat-bubble-left-right" class="w-10 h-10 text-white" />
                  </div>
                </div>
                <h2 class="text-2xl font-bold text-slate-200 mb-3">
                  Welcome to ScyllaDB RAG Demo
                </h2>
                <p class="text-slate-400 mb-6">
                  Start a new conversation or select an existing one from the sidebar
                </p>
                <button
                  phx-click="new_conversation"
                  class="px-6 py-3 bg-gradient-to-r from-blue-600 to-blue-500 hover:from-blue-500 hover:to-blue-400 text-white rounded-lg font-medium transition-all duration-200 shadow-lg shadow-blue-500/20"
                >
                  Start Chatting
                </button>
              </div>
            </div>
          <% else %>
            <%= if @messages == [] do %>
              <div class="h-full flex items-center justify-center">
                <p class="text-slate-500">Send a message to start the conversation</p>
              </div>
            <% else %>
              <%= for message <- @messages do %>
                <div class={[
                  "flex",
                  message["role"] == "user" && "justify-end",
                  message["role"] == "assistant" && "justify-start"
                ]}>
                  <div class={[
                    "max-w-3xl rounded-2xl px-6 py-4 shadow-lg",
                    message["role"] == "user" &&
                      "bg-gradient-to-r from-blue-600 to-blue-500 text-white",
                    message["role"] == "assistant" && "bg-slate-800/80 backdrop-blur-sm text-slate-200 border border-slate-700/50"
                  ]}>
                    <div class="flex items-start gap-3">
                      <div class={[
                        "flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center",
                        message["role"] == "user" && "bg-white/20",
                        message["role"] == "assistant" && "bg-purple-600/20"
                      ]}>
                        <.icon
                          name={message["role"] == "user" && "hero-user" || "hero-sparkles"}
                          class="w-5 h-5"
                        />
                      </div>
                      <div class="flex-1 min-w-0">
                        <p class="whitespace-pre-wrap break-words leading-relaxed">
                          {message["content"]}
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              <% end %>
            <% end %>

            <%= if @loading do %>
              <div class="flex justify-start">
                <div class="max-w-3xl rounded-2xl px-6 py-4 bg-slate-800/80 backdrop-blur-sm border border-slate-700/50">
                  <div class="flex items-center gap-3">
                    <div class="w-8 h-8 rounded-full bg-purple-600/20 flex items-center justify-center">
                      <.icon name="hero-sparkles" class="w-5 h-5 text-slate-400" />
                    </div>
                    <div class="flex gap-1.5">
                      <div class="w-2 h-2 bg-slate-500 rounded-full animate-bounce" style="animation-delay: 0ms;">
                      </div>
                      <div class="w-2 h-2 bg-slate-500 rounded-full animate-bounce" style="animation-delay: 150ms;">
                      </div>
                      <div class="w-2 h-2 bg-slate-500 rounded-full animate-bounce" style="animation-delay: 300ms;">
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            <% end %>
          <% end %>
        </div>

        <%!-- Input Area --%>
        <%= if @current_session_id do %>
          <div class="p-4 border-t border-slate-700/50 bg-slate-900/50 backdrop-blur-sm">
            <form phx-submit="send_message" class="max-w-4xl mx-auto">
              <div class="flex gap-3">
                <input
                  type="text"
                  name="message"
                  value={@message_input}
                  placeholder="Type your message..."
                  disabled={@loading}
                  class="flex-1 px-4 py-3 bg-slate-800 border border-slate-700 rounded-xl text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed"
                  id="message-input"
                  phx-hook=".FocusInput"
                />
                <button
                  type="submit"
                  disabled={@loading}
                  class="px-6 py-3 bg-gradient-to-r from-blue-600 to-blue-500 hover:from-blue-500 hover:to-blue-400 text-white rounded-xl font-medium transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-blue-500/20 hover:shadow-blue-500/40"
                >
                  <%= if @loading do %>
                    <.icon name="hero-arrow-path" class="w-5 h-5 animate-spin" />
                  <% else %>
                    <.icon name="hero-paper-airplane" class="w-5 h-5" />
                  <% end %>
                </button>
              </div>
            </form>
          </div>
        <% end %>
      </div>

      <%!-- Upload Modal --%>
      <%= if @show_upload_modal do %>
        <div class="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div class="bg-slate-900 rounded-2xl shadow-2xl max-w-2xl w-full border border-slate-700">
            <%!-- Modal Header --%>
            <div class="p-6 border-b border-slate-700 flex items-center justify-between">
              <div>
                <h2 class="text-2xl font-bold text-slate-200 flex items-center gap-2">
                  <.icon name="hero-arrow-up-tray" class="w-7 h-7 text-purple-400" />
                  Upload Documents
                </h2>
                <p class="text-sm text-slate-400 mt-1">Add PDF or Markdown files to your knowledge base</p>
              </div>
              <button
                phx-click="close_upload_modal"
                class="p-2 hover:bg-slate-800 rounded-lg transition-colors"
              >
                <.icon name="hero-x-mark" class="w-6 h-6 text-slate-400" />
              </button>
            </div>

            <%!-- Modal Content --%>
            <div class="p-6">
              <form phx-submit="submit_upload" phx-change="validate_upload" id="upload-form">
                <div class="space-y-4">
                  <%!-- File Upload Area --%>
                  <div class="border-2 border-dashed border-slate-600 rounded-xl p-8 text-center hover:border-purple-500 transition-colors">
                    <.live_file_input upload={@uploads.documents} class="hidden" />
                    <label for={@uploads.documents.ref} class="cursor-pointer block">
                      <div class="w-16 h-16 mx-auto bg-purple-600/20 rounded-full flex items-center justify-center mb-4">
                        <.icon name="hero-document-plus" class="w-8 h-8 text-purple-400" />
                      </div>
                      <p class="text-slate-300 font-medium mb-2">Click to select files</p>
                      <p class="text-sm text-slate-500">or drag and drop</p>
                      <p class="text-xs text-slate-600 mt-2">PDF, Markdown, or Text files (max 10MB each, up to 10 files)</p>
                    </label>
                  </div>

                  <%!-- Selected Files List --%>
                  <%= if length(@uploads.documents.entries) > 0 do %>
                    <div class="space-y-2">
                      <h3 class="text-sm font-medium text-slate-400">Selected Files</h3>
                      <%= for entry <- @uploads.documents.entries do %>
                        <div class="flex items-center justify-between bg-slate-800/50 rounded-lg p-3">
                          <div class="flex items-center gap-3 flex-1 min-w-0">
                            <.icon name="hero-document" class="w-5 h-5 text-purple-400 flex-shrink-0" />
                            <div class="flex-1 min-w-0">
                              <p class="text-sm text-slate-300 truncate">{entry.client_name}</p>
                              <p class="text-xs text-slate-500">{format_bytes(entry.client_size)}</p>
                            </div>
                          </div>
                          <button
                            type="button"
                            phx-click="cancel-upload"
                            phx-value-ref={entry.ref}
                            class="p-1 hover:bg-slate-700 rounded transition-colors"
                          >
                            <.icon name="hero-x-mark" class="w-4 h-4 text-slate-400" />
                          </button>
                        </div>
                      <% end %>
                    </div>
                  <% end %>

                  <%!-- Upload Progress --%>
                  <%= if length(@upload_progress) > 0 do %>
                    <div class="space-y-2">
                      <h3 class="text-sm font-medium text-slate-400">Upload Status</h3>
                      <%= for result <- @upload_progress do %>
                        <div class={[
                          "flex items-start gap-3 rounded-lg p-3 transition-all duration-200",
                          result.status == :success && "bg-green-900/20 border border-green-500/30",
                          result.status == :error && "bg-red-900/20 border border-red-500/30",
                          result.status == :uploading && "bg-blue-900/20 border border-blue-500/30",
                          result.status == :processing && "bg-purple-900/20 border border-purple-500/30"
                        ]}>
                          <%= cond do %>
                            <% result.status == :success -> %>
                              <.icon name="hero-check-circle" class="w-5 h-5 flex-shrink-0 text-green-400" />
                            <% result.status == :error -> %>
                              <.icon name="hero-x-circle" class="w-5 h-5 flex-shrink-0 text-red-400" />
                            <% result.status in [:uploading, :processing] -> %>
                              <.icon name="hero-arrow-path" class="w-5 h-5 flex-shrink-0 text-blue-400 animate-spin" />
                            <% true -> %>
                              <.icon name="hero-document" class="w-5 h-5 flex-shrink-0 text-slate-400" />
                          <% end %>
                          <div class="flex-1 min-w-0">
                            <p class="text-sm text-slate-300 font-medium">{result.filename}</p>
                            <p class={[
                              "text-xs mt-0.5",
                              result.status == :success && "text-green-400",
                              result.status == :error && "text-red-400",
                              result.status in [:uploading, :processing] && "text-blue-400",
                              true && "text-slate-500"
                            ]}>
                              {result.message}
                            </p>
                            <%= if result.chunks do %>
                              <div class="flex items-center gap-3 mt-2 text-xs text-slate-400">
                                <div class="flex items-center gap-1">
                                  <.icon name="hero-document-text" class="w-3.5 h-3.5" />
                                  <span>{result.chunks} chunks</span>
                                </div>
                                <%= if result.doc_id do %>
                                  <div class="flex items-center gap-1">
                                    <.icon name="hero-identification" class="w-3.5 h-3.5" />
                                    <span class="font-mono">{String.slice(result.doc_id, 0..7)}</span>
                                  </div>
                                <% end %>
                              </div>
                            <% end %>
                          </div>
                        </div>
                      <% end %>
                    </div>
                  <% end %>

                  <%!-- Upload Button --%>
                  <%= if length(@uploads.documents.entries) > 0 do %>
                    <button
                      type="submit"
                      disabled={@uploading}
                      class="w-full px-4 py-3 bg-gradient-to-r from-purple-600 to-purple-500 hover:from-purple-500 hover:to-purple-400 text-white rounded-lg font-medium transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-purple-500/20"
                    >
                      <%= if @uploading do %>
                        <.icon name="hero-arrow-path" class="w-5 h-5 inline mr-2 animate-spin" />
                        Uploading...
                      <% else %>
                        <.icon name="hero-arrow-up-tray" class="w-5 h-5 inline mr-2" />
                        Upload {length(@uploads.documents.entries)} file(s)
                      <% end %>
                    </button>
                  <% end %>
                </div>
              </form>
            </div>
          </div>
        </div>
      <% end %>

      <%!-- Debug Modal --%>
      <%= if @show_debug_modal && @debug_data do %>
        <div class="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4" phx-click="toggle_debug_modal">
          <div class="bg-slate-900 rounded-2xl shadow-2xl max-w-4xl w-full max-h-[90vh] overflow-hidden border border-slate-700" phx-click-away="toggle_debug_modal">
            <%!-- Modal Header --%>
            <div class="p-6 border-b border-slate-700 flex items-center justify-between">
              <div>
                <h2 class="text-2xl font-bold text-slate-200 flex items-center gap-2">
                  <.icon name="hero-code-bracket" class="w-7 h-7 text-purple-400" />
                  Context & Prompt Lineage
                </h2>
                <p class="text-sm text-slate-400 mt-1">How the response was generated</p>
              </div>
              <button
                phx-click="toggle_debug_modal"
                class="p-2 hover:bg-slate-800 rounded-lg transition-colors"
              >
                <.icon name="hero-x-mark" class="w-6 h-6 text-slate-400" />
              </button>
            </div>

            <%!-- Modal Content --%>
            <div class="overflow-y-auto max-h-[calc(90vh-120px)] p-6 space-y-6">
              <%!-- Short-term Memory --%>
              <%= if @debug_data["short_term"] && length(@debug_data["short_term"]) > 0 do %>
                <div class="bg-blue-900/20 border border-blue-500/30 rounded-xl p-5">
                  <h3 class="text-lg font-semibold text-blue-400 mb-3 flex items-center gap-2">
                    <.icon name="hero-clock" class="w-5 h-5" />
                    Short-term Memory
                    <span class="text-xs bg-blue-500/20 px-2 py-0.5 rounded">{length(@debug_data["short_term"])} messages</span>
                  </h3>
                  <div class="space-y-2">
                    <%= for msg <- @debug_data["short_term"] do %>
                      <div class="bg-slate-800/50 rounded-lg p-3">
                        <div class="text-xs text-slate-500 mb-1">{msg["role"]}</div>
                        <div class="text-sm text-slate-300">{msg["content"]}</div>
                      </div>
                    <% end %>
                  </div>
                </div>
              <% end %>

              <%!-- Long-term Conversation Memory --%>
              <%= if @debug_data["long_term"] && length(@debug_data["long_term"]) > 0 do %>
                <div class="bg-purple-900/20 border border-purple-500/30 rounded-xl p-5">
                  <h3 class="text-lg font-semibold text-purple-400 mb-3 flex items-center gap-2">
                    <.icon name="hero-chat-bubble-left-right" class="w-5 h-5" />
                    Long-term Conversation Memory
                    <span class="text-xs bg-purple-500/20 px-2 py-0.5 rounded">{length(@debug_data["long_term"])} results</span>
                  </h3>
                  <p class="text-xs text-slate-400 mb-3">Past conversation context retrieved via vector search</p>
                  <div class="space-y-2">
                    <%= for item <- @debug_data["long_term"] do %>
                      <div class="bg-slate-800/50 rounded-lg p-3">
                        <div class="flex items-center gap-2 mb-2">
                          <span class="text-xs px-2 py-0.5 rounded bg-blue-500/20 text-blue-400 border border-blue-500/30 flex items-center gap-1">
                            <.icon name="hero-sparkles" class="w-3 h-3" />
                            Conversation
                          </span>
                          <%= if item["similarity"] do %>
                            <span class="text-xs text-slate-500">
                              {Float.round(item["similarity"] * 100, 1)}% match
                            </span>
                          <% end %>
                        </div>
                        <div class="text-sm text-slate-300">{item["content"]}</div>
                      </div>
                    <% end %>
                  </div>
                </div>
              <% end %>

              <%!-- Document Enrichment --%>
              <%= if @debug_data["documents"] && length(@debug_data["documents"]) > 0 do %>
                <div class="bg-green-900/20 border border-green-500/30 rounded-xl p-5">
                  <h3 class="text-lg font-semibold text-green-400 mb-3 flex items-center gap-2">
                    <.icon name="hero-document-text" class="w-5 h-5" />
                    Document Enrichment
                    <span class="text-xs bg-green-500/20 px-2 py-0.5 rounded">{length(@debug_data["documents"])} results</span>
                  </h3>
                  <p class="text-xs text-slate-400 mb-3">Uploaded documents retrieved via vector search</p>
                  <div class="space-y-2">
                    <%= for item <- @debug_data["documents"] do %>
                      <div class="bg-slate-800/50 rounded-lg p-3">
                        <div class="flex items-center gap-2 mb-2">
                          <span class="text-xs px-2 py-0.5 rounded bg-green-500/20 text-green-400 border border-green-500/30 flex items-center gap-1">
                            <.icon name="hero-document-check" class="w-3 h-3" />
                            Uploaded Document
                          </span>
                          <%= if item["similarity"] do %>
                            <span class="text-xs text-slate-500">
                              {Float.round(item["similarity"] * 100, 1)}% match
                            </span>
                          <% end %>
                        </div>
                        <div class="text-sm text-slate-300">{item["content"]}</div>
                      </div>
                    <% end %>
                  </div>
                </div>
              <% end %>

              <%!-- Final Prompt --%>
              <%= if @debug_data["prompt"] do %>
                <div class="bg-amber-900/20 border border-amber-500/30 rounded-xl p-5">
                  <h3 class="text-lg font-semibold text-amber-400 mb-3 flex items-center gap-2">
                    <.icon name="hero-chat-bubble-left-ellipsis" class="w-5 h-5" />
                    Full Prompt Sent to LLM
                  </h3>
                  <pre class="bg-slate-800/50 rounded-lg p-4 text-xs text-slate-300 overflow-x-auto whitespace-pre-wrap">{@debug_data["prompt"]}</pre>
                </div>
              <% end %>

              <%!-- Final Messages --%>
              <%= if @debug_data["final_messages"] do %>
                <div class="bg-slate-800/50 border border-slate-600/30 rounded-xl p-5">
                  <h3 class="text-lg font-semibold text-slate-300 mb-3 flex items-center gap-2">
                    <.icon name="hero-chat-bubble-oval-left-ellipsis" class="w-5 h-5" />
                    Final Messages Context
                    <span class="text-xs bg-slate-600/30 px-2 py-0.5 rounded">{length(@debug_data["final_messages"])} messages</span>
                  </h3>
                  <div class="space-y-2">
                    <%= for msg <- @debug_data["final_messages"] do %>
                      <div class="bg-slate-900/50 rounded-lg p-3">
                        <div class="text-xs font-semibold mb-1" class={[
                          msg["role"] == "system" && "text-yellow-400",
                          msg["role"] == "user" && "text-blue-400",
                          msg["role"] == "assistant" && "text-purple-400"
                        ]}>
                          {String.upcase(msg["role"])}
                        </div>
                        <div class="text-sm text-slate-300">{msg["content"]}</div>
                      </div>
                    <% end %>
                  </div>
                </div>
              <% end %>
            </div>
          </div>
        </div>
      <% end %>
    </div>

    <script :type={Phoenix.LiveView.ColocatedHook} name=".ScrollToBottom">
      export default {
        mounted() {
          this.scrollToBottom();
        },
        updated() {
          this.scrollToBottom();
        },
        scrollToBottom() {
          this.el.scrollTop = this.el.scrollHeight;
        }
      }
    </script>

    <script :type={Phoenix.LiveView.ColocatedHook} name=".FocusInput">
      export default {
        mounted() {
          this.handleEvent("focus-input", () => {
            this.el.focus();
          });
        }
      }
    </script>
    """
  end

  defp format_time(nil), do: ""

  defp format_time(timestamp) when is_binary(timestamp) do
    case DateTime.from_iso8601(timestamp) do
      {:ok, dt, _} -> format_time(dt)
      _ -> ""
    end
  end

  defp format_time(%DateTime{} = dt) do
    now = DateTime.utc_now()
    diff = DateTime.diff(now, dt, :second)

    cond do
      diff < 60 -> "just now"
      diff < 3600 -> "#{div(diff, 60)}m ago"
      diff < 86400 -> "#{div(diff, 3600)}h ago"
      true -> "#{div(diff, 86400)}d ago"
    end
  end

  defp format_bytes(bytes) do
    cond do
      bytes >= 1_000_000 -> "#{Float.round(bytes / 1_000_000, 2)} MB"
      bytes >= 1_000 -> "#{Float.round(bytes / 1_000, 2)} KB"
      true -> "#{bytes} B"
    end
  end

  defp format_error({:http_error, status, body}) do
    if is_map(body) and Map.has_key?(body, "detail") do
      body["detail"]
    else
      "HTTP #{status} error"
    end
  end

  defp format_error(reason) when is_binary(reason), do: reason
  defp format_error(reason), do: inspect(reason)
end
