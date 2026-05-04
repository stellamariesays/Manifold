defmodule Mix.Tasks.Numinous.Open do
  @moduledoc """
  Open Voids from a JSON list of holes piped on stdin.

  Reads a JSON array from stdin, starts the Numinous application,
  opens a Void for each hole, lists active Voids, then exits.

  Called by the Python bridge:

      python3 -c "import json; print(json.dumps(holes))" | mix numinous.open

  Each hole is a JSON object:

      {"term": "agent-identity", "implied_by": ["agent-orchestration"], "pressure": 0.4}

  Or a plain string (term only, pressure defaults to 0.1):

      "agent-identity"

  ## Output

  Prints one line per active Void after opening:

      VOID agent-identity 0.4 [agent-orchestration, agent-consciousness]
      VOID solar-memory 0.3 [solar-memory-state-machine]
  """

  use Mix.Task
  require Logger

  @impl Mix.Task
  def run(_args) do
    # Start the application tree (Field + Registry)
    {:ok, _} = Application.ensure_all_started(:numinous)

    # Read JSON from stdin
    input = IO.read(:stdio, :all)

    holes =
      case Jason.decode(input) do
        {:ok, list} when is_list(list) -> list
        {:ok, other} ->
          Mix.shell().error("Expected a JSON array, got: #{inspect(other)}")
          []
        {:error, err} ->
          Mix.shell().error("JSON parse error: #{inspect(err)}")
          []
      end

    # Open Voids
    Numinous.Field.from_holes(holes)

    # Small wait for processes to start
    :timer.sleep(100)

    # Print results
    Numinous.Field.list_voids()
    |> Enum.each(fn v ->
      implied = Enum.join(v.implied_by, ", ")
      IO.puts("VOID #{v.term} #{v.pressure} [#{implied}]")
    end)
  end
end
