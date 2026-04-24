/**
 * bridge.test.js — Unit tests for the bridge event bus.
 *
 * Tests: emit/on routing, multiple listeners, off() removal,
 *        payload passing, unknown events don't throw.
 */

// The bridge module is pure JS with no external deps; import it directly.
// We use a dynamic path relative to the repo root.
import { bridge } from '../../public/nexal/bridge.js';

// Reset listener state between tests by using fresh closures.
// Since bridge._listeners is module-local we can't clear it directly —
// instead each test uses unique event names.

describe('bridge — basic routing', () => {
  test('on/emit: listener receives event', () => {
    const received = [];
    bridge.on('test:basic', (payload) => received.push(payload));
    bridge.emit('test:basic', { value: 42 });
    expect(received).toHaveLength(1);
    expect(received[0]).toEqual({ value: 42 });
  });

  test('payload is passed correctly', () => {
    let got;
    bridge.on('test:payload', (p) => { got = p; });
    bridge.emit('test:payload', { agent: { id: 'stella', hub: 'trillian' } });
    expect(got).toEqual({ agent: { id: 'stella', hub: 'trillian' } });
  });

  test('emit with no listeners does not throw', () => {
    expect(() => bridge.emit('test:no-listeners', { x: 1 })).not.toThrow();
  });

  test('emit unknown event does not throw', () => {
    expect(() => bridge.emit('completely-unknown-event-xyz', {})).not.toThrow();
  });

  test('emit with undefined payload does not throw', () => {
    bridge.on('test:undef-payload', () => {});
    expect(() => bridge.emit('test:undef-payload')).not.toThrow();
  });
});

describe('bridge — multiple listeners', () => {
  test('two listeners on the same event both fire', () => {
    const calls = [];
    bridge.on('test:multi', () => calls.push('a'));
    bridge.on('test:multi', () => calls.push('b'));
    bridge.emit('test:multi');
    expect(calls).toContain('a');
    expect(calls).toContain('b');
    expect(calls).toHaveLength(2);
  });

  test('listeners on different events are independent', () => {
    const resultsA = [], resultsB = [];
    bridge.on('test:eventA', (p) => resultsA.push(p));
    bridge.on('test:eventB', (p) => resultsB.push(p));
    bridge.emit('test:eventA', 'hello');
    expect(resultsA).toEqual(['hello']);
    expect(resultsB).toHaveLength(0);
    bridge.emit('test:eventB', 'world');
    expect(resultsB).toEqual(['world']);
    expect(resultsA).toHaveLength(1);
  });
});

describe('bridge — off()', () => {
  test('off() removes the specific listener', () => {
    const calls = [];
    const cb = (p) => calls.push(p);
    bridge.on('test:off', cb);
    bridge.emit('test:off', 1);
    bridge.off('test:off', cb);
    bridge.emit('test:off', 2);
    // Only the first emit should have been received
    expect(calls).toEqual([1]);
  });

  test('off() only removes the target listener, not others', () => {
    const callsA = [], callsB = [];
    const cbA = () => callsA.push('a');
    const cbB = () => callsB.push('b');
    bridge.on('test:off2', cbA);
    bridge.on('test:off2', cbB);
    bridge.off('test:off2', cbA);
    bridge.emit('test:off2');
    expect(callsA).toHaveLength(0);
    expect(callsB).toHaveLength(1);
  });

  test('off() on non-existent event/cb does not throw', () => {
    expect(() => bridge.off('test:nonexistent', () => {})).not.toThrow();
  });

  test('off() inside a listener callback is safe (no infinite loop)', () => {
    let count = 0;
    const cb = () => {
      count++;
      bridge.off('test:off-in-cb', cb);
    };
    bridge.on('test:off-in-cb', cb);
    bridge.emit('test:off-in-cb');
    bridge.emit('test:off-in-cb'); // second emit should not call cb
    expect(count).toBe(1);
  });
});

describe('bridge — error isolation', () => {
  test('a throwing listener does not prevent other listeners from running', () => {
    const calls = [];
    bridge.on('test:error-isolation', () => { throw new Error('boom'); });
    bridge.on('test:error-isolation', () => calls.push('survived'));
    // Should not throw at the bridge level
    expect(() => bridge.emit('test:error-isolation')).not.toThrow();
    expect(calls).toContain('survived');
  });
});
