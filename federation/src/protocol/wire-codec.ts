/**
 * Wire Codec — transparent JSON / MessagePack encoding for federation messages.
 *
 * MessagePack is ~30-50% smaller than JSON for typical protocol messages and
 * faster to parse. The codec auto-detects incoming format and sends in the
 * configured format.
 *
 * Detection: MessagePack messages start with byte 0x94 (fixarray of 4) or
 * other msgpack type bytes (0x80-0x8f for fixmap, 0x90-0x9f for fixarray, etc).
 * JSON messages always start with '{' (0x7b) or whitespace before it.
 */

import { encode as msgpackEncode, decode as msgpackDecode } from '@msgpack/msgpack'

export type WireFormat = 'json' | 'msgpack'

/**
 * Encode a message object to the specified wire format.
 */
export function encode(obj: unknown, format: WireFormat): Buffer | string {
  if (format === 'msgpack') {
    return Buffer.from(msgpackEncode(obj))
  }
  return JSON.stringify(obj)
}

/**
 * Decode an incoming message (auto-detects format).
 * Accepts string (JSON) or Buffer/Uint8Array (MessagePack).
 */
export function decode(data: string | Buffer | Uint8Array): unknown {
  if (typeof data === 'string') {
    return JSON.parse(data)
  }
  // Buffer or Uint8Array — check if it's actually JSON
  if (data instanceof Buffer || data instanceof Uint8Array) {
    const firstByte = data[0]
    // JSON starts with '{' (0x7b), '[' (0x5b), or whitespace (0x09, 0x0a, 0x0d, 0x20)
    if (firstByte === 0x7b || firstByte === 0x5b || firstByte === 0x09 || firstByte === 0x0a || firstByte === 0x0d || firstByte === 0x20) {
      return JSON.parse(typeof data === 'string' ? data : new TextDecoder().decode(data))
    }
    // Otherwise assume MessagePack
    return msgpackDecode(data)
  }
  throw new Error(`Unknown data type: ${typeof data}`)
}

/**
 * Detect wire format of incoming data.
 */
export function detectFormat(data: string | Buffer | Uint8Array): WireFormat {
  if (typeof data === 'string') return 'json'
  const firstByte = data[0]
  if (firstByte === 0x7b || firstByte === 0x5b || firstByte === 0x09 || firstByte === 0x0a || firstByte === 0x0d || firstByte === 0x20) {
    return 'json'
  }
  return 'msgpack'
}

/**
 * Estimate size savings of MessagePack over JSON for a given object.
 */
export function estimateSavings(obj: unknown): { jsonSize: number; msgpackSize: number; savings: number } {
  const json = JSON.stringify(obj)
  const msgpack = msgpackEncode(obj)
  return {
    jsonSize: json.length,
    msgpackSize: msgpack.length,
    savings: 1 - (msgpack.length / json.length),
  }
}
