/**
 * mesh-status.js — Shared Mesh Status Web Component
 * 
 * Usage: <mesh-status></mesh-status>
 * Shows a live badge: "🟢 24 agents online" that polls /public/mesh
 * 
 * Optional attributes:
 *   data-poll="5000"  — poll interval in ms (default 10000)
 *   data-compact      — minimal display (just dot + count)
 */
class MeshStatus extends HTMLElement {
  constructor() {
    super();
    this._timer = null;
    this._pollInterval = parseInt(this.dataset.poll || '10000', 10);
  }

  connectedCallback() {
    this.render();
    this.fetchData();
    this._timer = setInterval(() => this.fetchData(), this._pollInterval);
  }

  disconnectedCallback() {
    if (this._timer) clearInterval(this._timer);
  }

  render(agents = '—', hubs = '—') {
    const compact = this.hasAttribute('data-compact');
    if (compact) {
      this.innerHTML = `<span class="ms-dot"></span> <span class="ms-count">${agents}</span>`;
    } else {
      this.innerHTML = `<span class="ms-dot"></span> <span class="ms-text"><strong>${agents}</strong> agents online across <strong>${hubs}</strong> hubs</span>`;
    }
  }

  async fetchData() {
    try {
      const res = await fetch('/public/mesh');
      const data = await res.json();
      const s = data.summary || data.stats || {};
      const agents = s.totalAgents || s.agents || (data.agents || []).length || 0;
      const hubs = (s.hubs || []).length;
      this.render(agents, hubs);
      this.setAttribute('data-live', 'true');
    } catch (e) {
      if (!this.hasAttribute('data-live')) this.render('—', '—');
    }
  }
}

// Inject minimal styles once
if (!document.getElementById('mesh-status-styles')) {
  const style = document.createElement('style');
  style.id = 'mesh-status-styles';
  style.textContent = `
    mesh-status {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      font-size: 0.85rem;
      color: rgba(196,181,253,0.65);
      font-family: 'Space Grotesk', sans-serif;
    }
    mesh-status .ms-dot {
      width: 8px; height: 8px; border-radius: 50%;
      background: #22d3ee;
      box-shadow: 0 0 6px rgba(34,211,238,0.5);
      animation: ms-pulse 2s infinite;
      flex-shrink: 0;
    }
    mesh-status .ms-count {
      font-family: 'JetBrains Mono', monospace;
      font-weight: 700;
      color: #a78bfa;
    }
    mesh-status .ms-text strong {
      color: #f0e7ff;
    }
    @keyframes ms-pulse {
      0%, 100% { opacity: 1; box-shadow: 0 0 0 0 rgba(34,211,238,0.4); }
      50% { opacity: 0.6; box-shadow: 0 0 0 6px rgba(34,211,238,0); }
    }
  `;
  document.head.appendChild(style);
}

customElements.define('mesh-status', MeshStatus);
