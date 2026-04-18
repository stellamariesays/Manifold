defmodule Numinous.Application do
  @moduledoc false
  use Application

  @impl true
  def start(_type, _args) do
    children = [
      {Registry, keys: :unique, name: Numinous.VoidRegistry},
      Numinous.Field,
    ]

    opts = [strategy: :one_for_one, name: Numinous.Supervisor]
    Supervisor.start_link(children, opts)
  end
end
