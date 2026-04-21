# Nexal Progressive Web App (PWA)

Progressive Web App implementation of Nexal with offline capabilities and native mobile features.

## Features

- Offline federation data caching
- Push notifications for federation events
- Add to home screen capability
- Background sync for mesh updates
- Native mobile integration (camera, notifications, etc.)

## Files

- `manifest.json` - PWA manifest configuration
- `service-worker.js` - Offline caching and background sync
- `index.html` - PWA-enabled interface
- `offline.html` - Offline fallback page
- `install.js` - PWA installation prompts

## Installation

The PWA can be installed directly from the browser on mobile devices, providing a native app-like experience while maintaining web compatibility.

## Offline Features

- Cached federation mesh data
- Offline 3D visualization
- Queued actions when reconnecting
- Local federation node simulation