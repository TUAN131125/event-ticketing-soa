import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { resolve } from 'node:path';
import { parse } from 'yaml';

const frontendRoot = resolve(import.meta.dirname, '..');
const contractPath = resolve(frontendRoot, '../contracts/esb-public-api.yaml');
const contractBytes = await readFile(contractPath);
const document = parse(contractBytes.toString('utf8'));
const contractDigest = createHash('sha256').update(contractBytes).digest('hex');

const expectedOperations = new Map([
  ['POST /api/auth/register', 'registerIdentityAccountViaEsb'],
  ['POST /api/auth/login', 'loginIdentityAccountViaEsb'],
  ['POST /api/auth/refresh', 'refreshIdentitySessionViaEsb'],
  ['POST /api/auth/logout', 'logoutIdentitySessionViaEsb'],
  ['GET /api/auth/me', 'getCurrentIdentityPrincipalViaEsb'],
  ['GET /api/events', 'publicListEvents'],
  ['GET /api/events/{eventId}', 'publicGetEvent'],
  ['GET /api/events/{eventId}/seat-map', 'publicGetEventSeatMap'],
  ['POST /api/bookings', 'placeBooking'],
  ['GET /api/bookings', 'publicListBookings'],
  ['GET /api/bookings/{bookingId}', 'publicGetBooking'],
  ['POST /api/bookings/{bookingId}/cancel', 'publicCancelBooking'],
  ['GET /api/tickets', 'publicListTickets'],
  ['GET /api/tickets/{ticketId}', 'publicGetTicket'],
  ['GET /api/me/customer', 'getMyCustomerProfile'],
  ['PUT /api/me/customer', 'upsertMyCustomerProfile'],
  ['POST /api/admin/events', 'adminCreateEvent'],
  ['PUT /api/admin/events/{eventId}', 'adminReplaceEvent'],
  ['POST /api/admin/events/{eventId}/publish', 'adminPublishEvent'],
  ['POST /api/admin/events/{eventId}/pause', 'adminPauseEvent'],
  ['POST /api/admin/events/{eventId}/close', 'adminCloseEvent'],
  ['POST /api/admin/events/{eventId}/cancel', 'adminCancelEvent'],
  ['GET /api/admin/events/{eventId}/seat-inventory', 'adminGetSeatInventory'],
  ['PUT /api/admin/events/{eventId}/seat-inventory', 'adminConfigureSeatInventory'],
  ['POST /api/check-in/validate', 'validateTicketForCheckIn'],
  ['POST /api/check-in/tickets/{ticketId}', 'checkInTicketViaEsb'],
  ['POST /api/realtime/ws-tickets', 'issueRealtimeWebSocketTicket'],
  ['GET /api/traces/{correlationId}', 'getWorkflowTrace'],
  ['GET /api/health', 'aggregateHealth'],
]);

for (const [key, operationId] of expectedOperations) {
  const [method, path] = key.split(' ');
  const operation = document.paths?.[path]?.[method.toLowerCase()];
  if (!operation) throw new Error(`Missing ESB operation ${key}`);
  if (operation.operationId !== operationId) {
    throw new Error(`${key} operationId is ${operation.operationId}; expected ${operationId}`);
  }
}

const schemas = document.components?.schemas ?? {};
const requiredSchemas = [
  'RegisterRequest',
  'LoginRequest',
  'User',
  'TokenResponse',
  'PublicEvent',
  'SeatMapProjection',
  'PlaceBookingRequest',
  'BookingResult',
  'BookingListProjection',
  'TicketProjection',
  'TicketListProjection',
  'EventAdminRequest',
  'TicketValidationResult',
  'CheckInResult',
  'CustomerProfileInput',
  'CustomerProfileProjection',
  'AdminSeatInventoryProjection',
  'ConfigureSeatInventoryRequest',
  'ConfigureSeatInventoryResult',
];
for (const name of requiredSchemas) {
  if (!schemas[name]) throw new Error(`Missing frontend ESB schema ${name}`);
}

const unsupportedTicketFields = ['qrImageDataUrl', 'issuedAt', 'checkedInAt'];
for (const field of unsupportedTicketFields) {
  if (field in (schemas.TicketProjection.properties ?? {})) {
    throw new Error(`TicketProjection exposes backend-unsupported field ${field}`);
  }
}
for (const field of ['description', 'imageUrl']) {
  if (field in (schemas.PublicEvent.properties ?? {})) {
    throw new Error(`PublicEvent exposes backend-unsupported field ${field}`);
  }
}


const securitySchemes = document.components?.securitySchemes ?? {};
if (securitySchemes.UserJwt?.scheme !== 'bearer') {
  throw new Error('ESB OpenAPI does not declare UserJwt');
}
for (const [method, path] of [
  ['get', '/api/auth/me'],
  ['post', '/api/bookings'],
  ['get', '/api/tickets'],
  ['post', '/api/check-in/validate'],
]) {
  const security = document.paths?.[path]?.[method]?.security ?? [];
  if (!security.some((entry) => Object.hasOwn(entry, 'UserJwt'))) {
    throw new Error(`${method.toUpperCase()} ${path} is missing UserJwt`);
  }
}
for (const path of ['/api/auth/refresh', '/api/auth/logout']) {
  const security = document.paths?.[path]?.post?.security ?? [];
  if (!security.some((entry) => Object.hasOwn(entry, 'RefreshCookie') && Object.hasOwn(entry, 'CsrfCookie') && Object.hasOwn(entry, 'CsrfHeader'))) {
    throw new Error(`POST ${path} is missing refresh-cookie + CSRF security`);
  }
}

const aliases = await readFile(
  resolve(frontendRoot, 'shared-ui/src/frontend-esb-contract.ts'),
  'utf8',
);
if (!aliases.includes("components['schemas']")) {
  throw new Error('Frontend ESB aliases are not derived from generated OpenAPI types');
}
if (/export\s+interface\s+(Seat|Booking|Ticket|AdminEvent|CheckIn)/.test(aliases)) {
  throw new Error('Handwritten ESB wire interfaces are forbidden');
}



const adminClient = await readFile(resolve(frontendRoot, 'admin-web/src/api/esb.ts'), 'utf8');
if (!adminClient.includes('export type { AggregateHealth, PublicEvent }')) {
  throw new Error('Admin ESB client does not re-export page contract types');
}
if (!adminClient.includes('if (!ifMatch)')) {
  throw new Error('Admin check-in client does not fail closed without If-Match');
}

const customerClient = await readFile(
  resolve(frontendRoot, 'customer-web/src/api/esb-client.ts'),
  'utf8',
);
if (!customerClient.includes('export type { PlaceBookingRequest, RealtimeWsTicket }')) {
  throw new Error('Customer ESB client does not re-export hook/WebSocket contract types');
}

const adminApp = await readFile(resolve(frontendRoot, 'admin-web/src/App.tsx'), 'utf8');
if (adminApp.includes('path="/bookings"') || adminApp.includes("path='/bookings'")) {
  throw new Error('Undocumented admin Booking route remains connected to owner-scoped APIs');
}


const authSources = [
  resolve(frontendRoot, 'customer-web/src/api/auth-client.ts'),
  resolve(frontendRoot, 'admin-web/src/api/auth.ts'),
  resolve(frontendRoot, 'customer-web/.env.example'),
  resolve(frontendRoot, 'admin-web/.env.example'),
  resolve(frontendRoot, 'customer-web/Dockerfile'),
  resolve(frontendRoot, 'admin-web/Dockerfile'),
  resolve(frontendRoot, 'customer-web/vite.config.ts'),
  resolve(frontendRoot, 'customer-web/README.md'),
  resolve(frontendRoot, 'admin-web/README.md'),
  resolve(frontendRoot, 'README.md'),
];
for (const source of authSources) {
  const text = await readFile(source, 'utf8');
  if (text.includes('VITE_IDENTITY_API_URL') || text.includes('localhost:8009')) {
    throw new Error(`Frontend still references Identity directly: ${source}`);
  }
}
for (const source of authSources.slice(0, 2)) {
  const text = await readFile(source, 'utf8');
  if (!text.includes('/api/auth/')) {
    throw new Error(`Frontend auth client is not using the ESB façade: ${source}`);
  }
}
const browserBuildText = (await Promise.all(authSources.slice(2).map((source) => readFile(source, 'utf8')))).join('\n');
if (browserBuildText.includes('VITE_REALTIME_WS_URL') || browserBuildText.includes('localhost:8008')) {
  throw new Error('Frontend still permits direct Realtime port configuration');
}

const compose = parse(await readFile(resolve(frontendRoot, '../compose.yaml'), 'utf8'));
for (const service of ['customer-web', 'admin-web']) {
  const args = compose.services?.[service]?.build?.args ?? {};
  if (Object.keys(args).sort().join(',') !== 'VITE_ESB_API_URL') {
    throw new Error(`${service} Compose build exposes non-ESB browser URLs`);
  }
}

const generatedTypes = await readFile(
  resolve(frontendRoot, 'shared-ui/src/generated/esb-public-api.ts'),
  'utf8',
);
if (!generatedTypes.includes(`// Contract SHA-256: ${contractDigest}`)) {
  throw new Error('Checked-in ESB TypeScript types are stale; regenerate from canonical OpenAPI');
}
const generatedPairs = [
  ['providers/identity-service.yaml', 'identity-service.ts'],
  ['providers/realtime-status-service.yaml', 'realtime-service.ts'],
  ['providers/realtime-status.asyncapi.yaml', 'realtime-messages.ts'],
];
for (const [contractName, outputName] of generatedPairs) {
  const bytes = await readFile(resolve(frontendRoot, '../contracts', contractName));
  const digest = createHash('sha256').update(bytes).digest('hex');
  const output = await readFile(resolve(frontendRoot, 'shared-ui/src/generated', outputName), 'utf8');
  if (!output.includes(`// Contract SHA-256: ${digest}`)) {
    throw new Error(`Checked-in generated type is stale: ${outputName}`);
  }
}
if (!generatedTypes.includes('export interface paths')) {
  throw new Error('Generated ESB types do not expose path contracts');
}
if (!generatedTypes.includes('export interface operations')) {
  throw new Error('Generated ESB types do not expose operation contracts');
}
if (/export type (paths|operations) = Record<string, never>/.test(generatedTypes)) {
  throw new Error('Placeholder ESB path/operation types are forbidden');
}

console.log(`Verified ${expectedOperations.size} frontend ESB operations, ${requiredSchemas.length} schemas and generated type hash.`);
