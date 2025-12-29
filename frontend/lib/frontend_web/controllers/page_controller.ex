defmodule FrontendWeb.PageController do
  use FrontendWeb, :controller

  def home(conn, _params) do
    render(conn, :home)
  end
end
