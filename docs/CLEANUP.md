# Manifold Codebase Cleanup Candidates

This document lists files and modules that appear unused, superseded, or contain outdated references. **Do NOT delete these yet** — this is for review and gradual cleanup.

## Duplicate Module Structure

**Issue:** The codebase has parallel implementations in `core/` and `manifold/` directories.

### Affected Files

```
core/agent.py          ↔ manifold/agent.py
core/chart.py          ↔ manifold/chart.py  
core/atlas.py          ↔ manifold/atlas.py
core/topology.py       ↔ manifold/topology.py
core/registry.py       ↔ manifold/registry.py
core/sophia.py         ↔ manifold/sophia.py
core/store.py          ↔ manifold/store.py
core/blindspot.py      ↔ manifold/blindspot.py
core/bleed.py          ↔ manifold/bleed.py
core/semantic.py       ↔ manifold/semantic.py
core/transition.py     ↔ manifold/transition.py
core/bottleneck.py     ↔ manifold/bottleneck.py
core/persist.py        ↔ manifold/persist.py
```

**Recommendation:** Choose one directory as canonical. Current imports seem to favor `manifold/` over `core/`, but this needs verification.

## Broken Module References

### MRI Module

**Issue:** README previously referenced `manifold.mri` as an importable module, but it doesn't exist.

**Current state:** 
- `scripts/stella_mri.py` exists and works as a standalone script
- No `manifold/mri.py` or `core/mri.py` 
- Tests importing `manifold.mri` have been removed

**Action needed:** Either package MRI as a proper module or document that it's script-only.

### Missing Modules

Referenced in documentation but not found in codebase:
- `manifold.mri` — should be `scripts/stella_mri.py`
- Tests for non-existent modules may still exist

## Legacy Files (Candidates for Removal)

### Root Directory Scripts

These may be early prototypes that have been superseded:

```
data-detect-agent.py     # 10KB - appears to be early detection agent prototype
solar-detect-agent.py    # 11KB - appears to be specialized solar detection agent  
```

**Check:** Are these still used, or replaced by the federation agent system?

### Example/Prototype Files

```
contrib/                 # Directory purpose unclear
examples/                # May contain outdated examples
scripts/viz_feedback.py  # Visualization script - may be superseded
scripts/viz_trust.py     # Trust visualization - may be superseded  
scripts/mri_demo.py      # MRI demo - may be superseded by stella_mri.py
```

### Fog Module Structure

The fog implementation appears fragmented:

```
core/fog/delta.py        # Partial implementation
manifold/fog.py          # Consolidated implementation?
```

**Check:** Is `core/fog/` incomplete compared to `manifold/fog.py`?

## Outdated Documentation References

### In docs/VOID_LIFECYCLE.md

- References to specific file paths that may have moved
- Example commands that may be outdated
- Numinous integration steps may need verification

### In federation/SPEC.md

- References to specific Tailscale IPs that change
- Hub names that may no longer be active
- Phase completion status may be outdated

## Package Configuration Issues

### setup.py vs pyproject.toml

```
pyproject.toml           # Modern Python packaging
setup.py                # May not exist, but typical legacy location
```

**Check:** Ensure packaging configuration is consistent and modern.

### __init__.py Files

Some `__init__.py` files may have incorrect imports or expose wrong modules:

```
core/__init__.py         # May expose duplicate modules
manifold/__init__.py     # May have conflicting exports
```

## Test Coverage Issues

### Missing Tests

- `tests/test_mri.py` was removed due to missing `manifold.mri`
- Federation tests may be incomplete for some scaling features
- Core vs manifold module testing may be inconsistent

### Test Organization

```
tests/                   # Core Python tests
federation/tests/        # TypeScript federation tests  
```

Test structure is split and may have gaps.

## Image and Asset Files

Large binary assets that may be outdated:

```
manifold-feedback.png    # 306KB - documentation asset
manifold-trust.png       # 339KB - documentation asset  
```

**Check:** Are these still referenced in current documentation?

## Git and Development Files

### Submodules

```
.gitmodules             # May reference outdated or unused submodules
```

### Development Artifacts

```
.pytest_cache/          # Development artifact (should be .gitignored)
manifold_mesh.egg-info/ # Build artifact (should be .gitignored)
.venv/                  # Development environment (should be .gitignored)
```

## Federation Directory Organization

### Potential Node.js Bloat

```
federation/node_modules/ # Large dependency tree (300+ packages in find output)
```

**Check:** Are all dependencies actually needed, or can some be dev-only?

### TypeScript Build Output

```
federation/dist/         # May not exist yet, but should be .gitignored when created
```

## Action Plan

### Phase 1: Inventory (Current)
- [x] Document all potential cleanup candidates
- [x] Identify broken references  
- [x] Note duplicate implementations

### Phase 2: Analysis (Next)
- [ ] Determine which core/ vs manifold/ modules are canonical
- [ ] Verify which scripts are still in use
- [ ] Check test coverage for each module
- [ ] Audit federation dependency tree

### Phase 3: Cleanup (Future)  
- [ ] Remove or consolidate duplicate modules
- [ ] Fix broken imports and references
- [ ] Archive or remove unused scripts
- [ ] Standardize test organization
- [ ] Update documentation to match actual code structure

### Phase 4: Packaging (Future)
- [ ] Ensure clean package structure
- [ ] Verify all imports work correctly
- [ ] Package MRI as module if needed
- [ ] Clean up build artifacts and git configuration

## Notes

- **Priority:** Fix duplicate module structure first (core/ vs manifold/)
- **Safety:** Keep backups before removing anything
- **Testing:** Verify all examples and tests work after cleanup
- **Documentation:** Update all docs to match cleaned structure

This cleanup should be done gradually, with testing after each change to ensure nothing breaks.