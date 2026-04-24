/**
 * data.js — Federation mesh data loading.
 * Exports: loadAgentsAndBuild
 *
 * Calls build/update functions once mesh data is fetched.
 */

/**
 * @param {{ buildSpiderWeb, buildAgentTopologies, buildCentralNexus, updateAgentsList, updateStatusPanel, animate }} callbacks
 */
export async function loadAgentsAndBuild(callbacks) {
  let agents = [];

  try {
    const response = await fetch('/api/mesh');
    const meshData = await response.json();
    if (meshData && meshData.agents) {
      agents = meshData.agents;
      // Store mesh data globally for data highways (animation.js reads it)
      window._meshData = meshData;
      console.log('Mesh data loaded:', meshData.agents.length, 'agents,',
                  meshData.darkCircles ? meshData.darkCircles.length : 0, 'darkCircles');
    }
  } catch (e) {
    console.log('Using demo agents (API offline)');
    agents = [
      // HOG Hub (green)
      { id: 'solar-detect', hub: 'hog', capabilities: ['monitoring'], position: [-8, 2, -2] },
      { id: 'solar-sites', hub: 'hog', capabilities: ['web-deploy'], position: [-6, 0, -1] },
      { id: 'cron-monitor', hub: 'hog', capabilities: ['scheduling'], position: [-7, -1, 0] },

      // TRILLIAN Hub (purple)
      { id: 'stella', hub: 'trillian', capabilities: ['guidance'], position: [6, 3, 0] },
      { id: 'manifold', hub: 'trillian', capabilities: ['topology'], position: [8, 1, 1] },
      { id: 'argue', hub: 'trillian', capabilities: ['debate'], position: [7, 0, -2] },
      { id: 'braid', hub: 'trillian', capabilities: ['solar-prediction'], position: [5, 2, 2] },

      // THEFOG Hub (purple)
      { id: 'void-watcher', hub: 'thefog', capabilities: ['void-scan'], position: [0, 4, 8] },
      { id: 'reach-scanner', hub: 'thefog', capabilities: ['mesh-probe'], position: [-1, 3, 6] },
      { id: 'sentry', hub: 'thefog', capabilities: ['monitoring'], position: [1, 5, 7] },
      { id: 'sophia', hub: 'thefog', capabilities: ['void-depth'], position: [0, 6, 5] },
    ];
  }

  callbacks.buildSpiderWeb();
  callbacks.buildAgentTopologies(agents);
  callbacks.buildCentralNexus();
  callbacks.updateAgentsList(agents);
  callbacks.updateStatusPanel(agents);

  callbacks.animate();
}
