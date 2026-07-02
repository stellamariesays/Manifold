// ── Entry point ─────────────────────────────────────────────────────

import { CloudGateway } from './gateway.js';

const port = parseInt(process.env['PORT'] ?? '3000', 10);
const federationApiUrl = process.env['FEDERATION_API_URL'] ?? 'http://localhost:8767';
const hubName = process.env['FEDERATION_HUB_NAME'] ?? 'trillian';

const gateway = new CloudGateway({
  port,
  federationApiUrl,
  hubName,
  stripeSecretKey: process.env['STRIPE_SECRET_KEY'],
  stripeWebhookSecret: process.env['STRIPE_WEBHOOK_SECRET'],
  openaiKey: process.env['OPENAI_API_KEY'],
  anthropicKey: process.env['ANTHROPIC_API_KEY'],
  googleKey: process.env['GOOGLE_API_KEY'],
  localModelUrl: process.env['LOCAL_MODEL_URL'],
});

gateway.start().catch((err) => {
  console.error('Failed to start Manifold Cloud Gateway:', err);
  process.exit(1);
});

// Graceful shutdown
const shutdown = async (signal: string) => {
  console.log(`\n[gateway] ${signal} received — shutting down...`);
  await gateway.stop();
  process.exit(0);
};

process.on('SIGINT', () => void shutdown('SIGINT'));
process.on('SIGTERM', () => void shutdown('SIGTERM'));
