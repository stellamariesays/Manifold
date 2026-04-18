defmodule Numinous do
  @moduledoc """
  Numinous — the ground the mesh floats in.

  Manifold maps what a cognitive mesh knows: named agents, explicit transitions,
  Sophia scores. Numinous holds what the mesh implies but hasn't named — the dark
  circles in the background of the MRI.

  Each dark circle is a `Numinous.Void` — a live process. It exists, it has
  pressure, it can receive messages. When an agent finally covers it, the Void
  exits: it has become Manifold.

  ## Relationship to Manifold

      Manifold          Numinous
      ─────────         ────────
      Named nodes  ←→   Void processes
      Sophia score  ←   Pressure map
      atlas.holes() →   Field.from_holes/1
      Agent covers  →   Field.name_void/2

  ## Quick start

      # From a Manifold atlas (via Python JSON export or direct):
      holes = [
        %{"term" => "agent-identity",  "implied_by" => ["agent-orchestration"], "pressure" => 0.4},
        %{"term" => "solar-memory",    "implied_by" => ["solar-memory-state-machine"], "pressure" => 0.3},
      ]

      Numinous.open(holes)
      Numinous.voids()
      # => [%{term: "agent-identity", pressure: 0.4, ...}, ...]

      Numinous.name("agent-identity", "stella")
      # void: agent-identity named by stella after 412ms — becoming manifold

  ## The seam

  Glossolalia in Manifold fires at the boundary between the explicit mesh and the
  implicit ground. Numinous is that ground. The Voids are what the glossolalia
  probe touches when coordination pressure drops to 0.
  """

  @doc "Open Void processes for a list of holes."
  defdelegate open(holes), to: Numinous.Field, as: :from_holes

  @doc "List all active Voids, sorted by pressure descending."
  defdelegate voids(), to: Numinous.Field, as: :list_voids

  @doc "Name a Void — an agent has covered this region."
  defdelegate name(term, agent), to: Numinous.Field, as: :name_void

  @doc "Pressure map — %{term => pressure} for all active Voids."
  defdelegate pressure_map(), to: Numinous.Field, as: :pressure_map

  @doc "Open a single Void directly."
  defdelegate void(term, implied_by \\ [], pressure \\ 0.0), to: Numinous.Field, as: :open_void
end
