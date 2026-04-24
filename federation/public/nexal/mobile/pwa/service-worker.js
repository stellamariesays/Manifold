// Nexal Network PWA Service Worker
const CACHE_NAME = 'nexal-pwa-v1';
const FEDERATION_CACHE = 'nexal-federation-data-v1';

// Core files to cache for offline functionality
const CORE_FILES = [
  '/nexal/mobile/pwa/',
  '/nexal/mobile/pwa/index.html',
  '/nexal/mobile/pwa/manifest.json',
  '/nexal/shared/federation-client.js',
  '/nexal/shared/3d-core.js',
  'https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js',
  'https://fonts.googleapis.com/css2?family=Rajdhani:wght@300;400;600&display=swap'
];

// Federation API endpoints to cache
const FEDERATION_ENDPOINTS = [
  '/api/agents',
  '/api/mesh',
  '/api/capabilities',
  '/api/hubs'
];

// Install event - cache core files
self.addEventListener('install', event => {
  console.log('Nexal PWA Service Worker installing...');
  
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        console.log('Caching core PWA files');
        return cache.addAll(CORE_FILES);
      })
      .then(() => self.skipWaiting())
  );
});

// Activate event - cleanup old caches
self.addEventListener('activate', event => {
  console.log('Nexal PWA Service Worker activating...');
  
  event.waitUntil(
    caches.keys()
      .then(cacheNames => {
        return Promise.all(
          cacheNames
            .filter(cacheName => 
              cacheName.startsWith('nexal-') && 
              cacheName !== CACHE_NAME && 
              cacheName !== FEDERATION_CACHE
            )
            .map(cacheName => {
              console.log('Deleting old cache:', cacheName);
              return caches.delete(cacheName);
            })
        );
      })
      .then(() => self.clients.claim())
  );
});

// Fetch event - serve from cache with network fallback
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  
  // Handle federation API requests
  if (FEDERATION_ENDPOINTS.some(endpoint => url.pathname.includes(endpoint))) {
    event.respondWith(
      handleFederationRequest(event.request)
    );
    return;
  }
  
  // Handle core files
  if (CORE_FILES.some(file => event.request.url.includes(file))) {
    event.respondWith(
      caches.match(event.request)
        .then(response => {
          if (response) {
            return response;
          }
          
          return fetch(event.request)
            .then(response => {
              const responseClone = response.clone();
              caches.open(CACHE_NAME)
                .then(cache => {
                  cache.put(event.request, responseClone);
                });
              return response;
            });
        })
    );
    return;
  }
  
  // Default: network first, cache fallback
  event.respondWith(
    fetch(event.request)
      .catch(() => caches.match(event.request))
  );
});

// Handle federation API requests with caching and offline fallback
async function handleFederationRequest(request) {
  const cache = await caches.open(FEDERATION_CACHE);
  
  try {
    // Try to fetch fresh data
    const networkResponse = await fetch(request);
    
    if (networkResponse.ok) {
      // Cache the fresh data
      cache.put(request, networkResponse.clone());
      return networkResponse;
    }
  } catch (error) {
    console.log('Network request failed, using cached data:', error);
  }
  
  // Fallback to cached data
  const cachedResponse = await cache.match(request);
  if (cachedResponse) {
    return cachedResponse;
  }
  
  // Ultimate fallback: mock federation data
  return new Response(JSON.stringify(generateFallbackData(request.url)), {
    headers: {
      'Content-Type': 'application/json',
      'X-Nexal-Fallback': 'true'
    }
  });
}

// Generate fallback federation data when offline
function generateFallbackData(url) {
  if (url.includes('/agents')) {
    return {
      agents: Array(23).fill().map((_, i) => ({
        id: `agent-${i}`,
        name: `Agent-${i}`,
        status: 'offline',
        capabilities: [`cap-${i}`, `cap-${i+23}`]
      })),
      timestamp: Date.now(),
      source: 'offline-fallback'
    };
  }
  
  if (url.includes('/mesh')) {
    return {
      hubs: ['trillian', 'hog', 'thefog', 'bobiverse'],
      connections: 23,
      status: 'offline',
      timestamp: Date.now(),
      source: 'offline-fallback'
    };
  }
  
  if (url.includes('/capabilities')) {
    return {
      capabilities: Array(60).fill().map((_, i) => ({
        id: `cap-${i}`,
        name: `Capability-${i}`,
        agents: Math.floor(Math.random() * 5) + 1
      })),
      timestamp: Date.now(),
      source: 'offline-fallback'
    };
  }
  
  return { error: 'No fallback data available' };
}

// Background sync for queued actions
self.addEventListener('sync', event => {
  if (event.tag === 'federation-sync') {
    event.waitUntil(syncFederationData());
  }
});

async function syncFederationData() {
  console.log('Syncing federation data in background...');
  
  try {
    // Sync all federation endpoints
    for (const endpoint of FEDERATION_ENDPOINTS) {
      const response = await fetch(endpoint);
      if (response.ok) {
        const cache = await caches.open(FEDERATION_CACHE);
        cache.put(endpoint, response.clone());
      }
    }
    
    // Notify clients of successful sync
    self.clients.matchAll().then(clients => {
      clients.forEach(client => {
        client.postMessage({
          type: 'FEDERATION_SYNC_COMPLETE',
          timestamp: Date.now()
        });
      });
    });
    
  } catch (error) {
    console.error('Background sync failed:', error);
  }
}

// Push notifications for federation events
self.addEventListener('push', event => {
  const options = {
    body: event.data ? event.data.text() : 'Federation network update available',
    icon: '/nexal/mobile/pwa/icon-192.png',
    badge: '/nexal/mobile/pwa/badge-72.png',
    tag: 'federation-update',
    data: {
      url: '/nexal/mobile/pwa/'
    },
    actions: [
      {
        action: 'view',
        title: 'View Network',
        icon: '/nexal/mobile/pwa/action-view.png'
      },
      {
        action: 'dismiss',
        title: 'Dismiss'
      }
    ]
  };
  
  event.waitUntil(
    self.registration.showNotification('Nexal Network', options)
  );
});

// Handle notification clicks
self.addEventListener('notificationclick', event => {
  event.notification.close();
  
  if (event.action === 'view' || !event.action) {
    event.waitUntil(
      clients.openWindow('/nexal/mobile/pwa/')
    );
  }
});