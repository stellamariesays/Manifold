defmodule Numinous.Field do
  @moduledoc """
  The Field holds all Voids.

  A DynamicSupervisor that starts and tracks Void processes — one per dark circle
  in the cognitive mesh. When a Void is named, it exits and the Field forgets it.

  The Field is the right hemisphere's working memory: it knows what exists
  without names, tracks the pressure on each region, and releases them
  when the left hemisphere finally arrives.

  ## Usage

      {:ok, _} = Numinous.Field.start_link([])

      Numinous.Field.open_void("agent-identity", ["agent-orchestration"], 0.4)
      Numinous.Field.open_void("solar-memory", ["solar-memory-state-machine"], 0.3)

      Numinous.Field.list_voids()
      # => [%{term: "agent-identity", pressure: 0.4, ...}, ...]

      Numinous.Field.name_void("agent-identity", "stella")
      # => :named — Void exits, Field removes it
  """

  use DynamicSupervisor
  require Logger

  @registry Numinous.VoidRegistry
  @max_voids 5

  def start_link(init_arg) do
    DynamicSupervisor.start_link(__MODULE__, init_arg, name: __MODULE__)
  end

  @impl true
  def init(_init_arg) do
    DynamicSupervisor.init(strategy: :one_for_one)
  end

  # ── Public API ───────────────────────────────────────────────────────────────

  @doc "Open a Void for a hole in the mesh."
  def open_void(term, implied_by \\ [], pressure \\ 0.0) do
    spec = %{
      id: {Numinous.Void, term},
      start: {Numinous.Void, :open, [term, implied_by, pressure]},
      restart: :temporary,
    }
    DynamicSupervisor.start_child(__MODULE__, spec)
  end

  @doc "List all active Voids and their current state."
  def list_voids do
    Registry.select(@registry, [{{:"$1", :"$2", :"$3"}, [], [{{:"$1", :"$2"}}]}])
    |> Enum.map(fn {_term, pid} ->
      if Process.alive?(pid) do
        Numinous.Void.query(pid)
      else
        nil
      end
    end)
    |> Enum.reject(&is_nil/1)
    |> Enum.sort_by(& &1.pressure, :desc)
  end

  @doc "Name a Void — an agent has covered this region. The Void exits."
  def name_void(term, agent) do
    case Registry.lookup(@registry, term) do
      [{pid, _}] -> Numinous.Void.name(pid, agent)
      []         -> {:error, :not_found}
    end
  end

  @doc "Returns a pressure map: %{term => pressure} for all active Voids."
  def pressure_map do
    list_voids()
    |> Map.new(fn v -> {v.term, v.pressure} end)
  end

  @doc "Open Voids from a list of hole maps (from Manifold atlas.holes() output). Capped at @max_voids."
  def from_holes(holes) when is_list(holes) do
    holes
    |> Enum.take(@max_voids)
    |> Enum.each(fn hole ->
      term     = Map.get(hole, "term", hole)
      implied  = Map.get(hole, "implied_by", [])
      pressure = Map.get(hole, "pressure", 0.1)
      open_void(term, implied, pressure)
    end)
    :ok
  end
end
