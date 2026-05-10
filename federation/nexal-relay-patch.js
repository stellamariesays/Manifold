/**
 * nexal-relay-patch.js
 * 
 * Drop-in wire logging for nexal's federation relay.
 * Identifies where body gets stripped from task_result.
 * 
 * Apply: patch the two functions in your dist/server/task-router.js
 * 
 * 1. In handleResult(), add as FIRST line after the function open:
 *    console.log(`[relay:entry] task_result id=${result.id} status=${result.status} body=${result.body ? JSON.stringify(result.body).substring(0,200) : 'MISSING'}`);
 *
 * 2. In sendResult(), add as FIRST line after the function open:
 *    console.log(`[relay:egress] task_result id=${result.id} status=${result.status} body=${msg.body ? JSON.stringify(msg.body).substring(0,200) : 'MISSING'} to=${originHub || 'client'}`);
 *
 * Then restart the federation service and send a test task.
 * 
 * Reading the logs:
 * - body present at entry but missing at egress → relay bug (sendResult strips it)
 * - body missing at entry → echo handler isn't populating it
 * 
 * Clean this up after diagnosing — remove the two console.logs.
 */
