defmodule Numinous.Void do
  @moduledoc """
  A Void is a dark circle — a region that exists in the mesh's negative space.

  It has no agent. No chart covers it. It is implied by the surrounding vocabulary
  but has not been named. It lives as a process.

  A Void is not a gap in knowledge. It is prior to knowledge. It exists because
  the mesh implies it — not because any agent noticed it was missing.

  ## Lifecycle

      Numinous.Void.open("agent-identity", ["agent-orchestration", "agent-consciousness"], 0.4)
      # => {:ok, pid}

      Numinous.Void.query(pid)
      # => %{term: "agent-identity", implied_by: [...], pressure: 0.4, age_ms: 1200}

      Numinous.Void.name(pid, "stella")
      # => :named — process exits cleanly

  When named, the Void logs its passage and stops. It has become Manifold.
  """

  use GenServer
  require Logger

  # ── Public API ──────────────────────────────────────────────────────────────

  @doc "Open a Void for the given hole term."
  def open(term, implied_by \\ [], pressure \\ 0.0) do
    GenServer.start_link(__MODULE__, %{
      term: term,
      implied_by: implied_by,
      pressure: pressure,
      born_at: System.monotonic_time(:millisecond),
    }, name: {:via, Registry, {Numinous.VoidRegistry, term}})
  end

  @doc "Query the Void — what are you, who surrounds you, how much pressure?"
  def query(pid) do
    GenServer.call(pid, :query)
  end

  @doc "An agent is now covering this region. The Void becomes Manifold and exits."
  def name(pid, agent) do
    GenServer.call(pid, {:name, agent})
  end

  @doc "Update the pressure on this Void."
  def pressure(pid, delta) do
    GenServer.cast(pid, {:pressure, delta})
  end

  # ── GenServer callbacks ──────────────────────────────────────────────────────

  @impl true
  def init(state) do
    Logger.info("void: #{state.term} opened — pressure #{Float.round(state.pressure, 3)}")
    {:ok, state}
  end

  @impl true
  def handle_call(:query, _from, state) do
    age_ms = System.monotonic_time(:millisecond) - state.born_at
    reply = Map.put(state, :age_ms, age_ms) |> Map.delete(:born_at)
    {:reply, reply, state}
  end

  @impl true
  def handle_call({:name, agent}, _from, state) do
    age_ms = System.monotonic_time(:millisecond) - state.born_at
    Logger.info(
      "void: #{state.term} named by #{agent} after #{age_ms}ms — becoming manifold"
    )
    {:stop, :normal, :named, state}
  end

  @impl true
  def handle_cast({:pressure, delta}, state) do
    new_pressure = min(1.0, max(0.0, state.pressure + delta))
    {:noreply, %{state | pressure: new_pressure}}
  end
end
