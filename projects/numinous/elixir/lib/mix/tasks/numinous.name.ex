defmodule Mix.Tasks.Numinous.Name do
  @moduledoc """
  Name a Void — mark it as covered by an agent. The Void exits: it becomes Manifold.

  Usage:

      mix numinous.name <term> <agent>

  Example:

      mix numinous.name identity-modeling stella

  Opens the Void briefly, calls Numinous.name/2, logs the passage, exits.
  """

  use Mix.Task
  require Logger

  @impl Mix.Task
  def run([term, agent]) do
    {:ok, _} = Application.ensure_all_started(:numinous)

    # Open the void first (so there's a process to name)
    case Numinous.Field.open_void(term, [], 0.0) do
      {:ok, pid} ->
        result = Numinous.Void.name(pid, agent)
        IO.puts("NAMED #{term} by #{agent} — #{result}")

      {:error, {:already_started, pid}} ->
        result = Numinous.Void.name(pid, agent)
        IO.puts("NAMED #{term} by #{agent} (was already open) — #{result}")

      {:error, reason} ->
        IO.puts("ERROR opening void #{term}: #{inspect(reason)}")
        System.halt(1)
    end
  end

  def run(_) do
    Mix.shell().error("Usage: mix numinous.name <term> <agent>")
    System.halt(1)
  end
end
