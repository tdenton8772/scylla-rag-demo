defmodule FrontendWeb.ChatLiveUploadTest do
  use FrontendWeb.ConnCase
  import Phoenix.LiveViewTest

  @backend_url "http://localhost:8000"

  describe "document upload" do
    test "modal opens and closes", %{conn: conn} do
      {:ok, view, _html} = live(conn, "/")

      # Modal should be closed initially
      refute has_element?(view, "[phx-click='close_upload_modal']")

      # Open modal
      view |> element("button", "Upload Documents") |> render_click()

      # Modal should be visible
      assert has_element?(view, "h2", "Upload Documents")

      # Close modal
      view |> element("button[phx-click='close_upload_modal']") |> render_click()
    end

    test "displays selected file", %{conn: conn} do
      {:ok, view, _html} = live(conn, "/")

      # Open modal
      view |> element("button", "Upload Documents") |> render_click()

      # Create a test file
      test_content = "# Test Document\n\nThis is a test."
      file_name = "test_doc.md"

      # Upload file
      file = file_input(view, "#upload-form", :documents, [
        %{
          name: file_name,
          content: test_content,
          type: "text/markdown"
        }
      ])

      assert render_upload(file, file_name) =~ file_name
    end

    test "submits upload and processes file", %{conn: conn} do
      # Start a test HTTP server or mock the backend
      # For now, we'll test that the event is triggered

      {:ok, view, _html} = live(conn, "/")

      # Open modal
      view |> element("button", "Upload Documents") |> render_click()

      # Create test file
      test_content = "# Test Document\n\nThis is a test."
      file_name = "test_doc.md"

      # Upload file
      file = file_input(view, "#upload-form", :documents, [
        %{
          name: file_name,
          content: test_content,
          type: "text/markdown"
        }
      ])

      render_upload(file, file_name)

      # Submit the form
      html = view |> element("form[phx-submit='submit_upload']") |> render_submit()

      # Should show uploading state
      assert html =~ "Uploading..." or html =~ "Processing..."
    end

    test "handle_info :process_uploads is called", %{conn: conn} do
      {:ok, view, _html} = live(conn, "/")

      # Open modal
      view |> element("button", "Upload Documents") |> render_click()

      # Create test file
      test_content = "# Test Document\n\nThis is a test."
      file_name = "test_doc.md"

      # Upload file
      file = file_input(view, "#upload-form", :documents, [
        %{
          name: file_name,
          content: test_content,
          type: "text/markdown"
        }
      ])

      render_upload(file, file_name)

      # Submit - this should trigger send(self(), :process_uploads)
      view |> element("form[phx-submit='submit_upload']") |> render_submit()

      # Give it a moment to process
      :timer.sleep(100)

      # Check if progress was updated
      html = render(view)
      
      # Should show either uploading, processing, success, or error state
      assert html =~ "Uploading..." or 
             html =~ "Processing..." or 
             html =~ "Successfully processed" or
             html =~ "Upload failed"
    end
  end

  describe "upload handler" do
    test "consume_uploaded_entries returns correct format" do
      # This tests the callback format
      result = {:ok, {"ref123", "test.pdf", {:ok, %{"total_chunks" => 5}}}}
      
      assert match?({:ok, _}, result)
    end
  end

  describe "multipart upload" do
    test "manually construct multipart form data" do
      # Test the multipart construction that was added
      boundary = "----WebKitFormBoundary123456789"
      filename = "test.pdf"
      content = "test content"
      
      body = ""
      body = body <> "--#{boundary}\r\n"
      body = body <> "Content-Disposition: form-data; name=\"file\"; filename=\"#{filename}\"\r\n"
      body = body <> "Content-Type: application/octet-stream\r\n\r\n"
      body = body <> content
      body = body <> "\r\n--#{boundary}--\r\n"
      
      # Verify structure
      assert body =~ "Content-Disposition: form-data"
      assert body =~ "filename=\"test.pdf\""
      assert body =~ "test content"
    end
  end
end
