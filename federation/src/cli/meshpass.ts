#!/usr/bin/env node
/**
 * MeshPass CLI: Generate and manage MeshPass credentials.
 * 
 * Usage:
 *   npx meshpass generate
 *   npx meshpass info
 *   npx meshpass export
 *   npx meshpass import <file>
 *   npx meshpass sign <message>
 *   npx meshpass verify <message> <signature> <publicKey>
 */

import { readFileSync, writeFileSync } from 'fs'
import { MeshPass, MeshID, createAuthMessage, type MeshPassKeyData } from '../identity/index.js'

const COMMANDS = {
  generate: 'Generate a new MeshPass',
  info: 'Show MeshPass information',
  export: 'Export MeshPass for import on another machine',
  import: 'Import MeshPass from file',
  sign: 'Sign a message with MeshPass',
  verify: 'Verify a message signature',
  auth: 'Generate authentication message'
}

function printUsage(): void {
  console.log('MeshPass CLI - Cryptographic identity for Manifold mesh')
  console.log()
  console.log('Usage: npx tsx meshpass.ts <command> [options]')
  console.log()
  console.log('Commands:')
  for (const [cmd, desc] of Object.entries(COMMANDS)) {
    console.log(`  ${cmd.padEnd(12)} ${desc}`)
  }
  console.log()
  console.log('Examples:')
  console.log('  npx tsx meshpass.ts generate')
  console.log('  npx tsx meshpass.ts info')
  console.log('  npx tsx meshpass.ts export > my-meshpass.json')
  console.log('  npx tsx meshpass.ts import my-meshpass.json')
  console.log('  npx tsx meshpass.ts sign "Hello, mesh!"')
  console.log('  npx tsx meshpass.ts auth stella@satelliteA')
}

function readPassphrase(prompt: string): string | undefined {
  // In a real CLI, you'd use a proper password input library
  // For now, just read from command line or environment
  const passphrase = process.env.MESHPASS_PASSPHRASE
  if (passphrase) {
    console.log(`Using passphrase from MESHPASS_PASSPHRASE environment variable`)
    return passphrase
  }
  
  console.log(`${prompt} (set MESHPASS_PASSPHRASE env var to avoid this prompt)`)
  return undefined
}

async function main(): Promise<void> {
  const args = process.argv.slice(2)
  const command = args[0]

  if (!command || !Object.keys(COMMANDS).includes(command)) {
    printUsage()
    process.exit(1)
  }

  try {
    switch (command) {
      case 'generate':
        await generateMeshPass()
        break
        
      case 'info':
        await showInfo()
        break
        
      case 'export':
        await exportMeshPass()
        break
        
      case 'import':
        const importFile = args[1]
        if (!importFile) {
          console.error('Error: Import file required')
          console.log('Usage: npx tsx meshpass.ts import <file>')
          process.exit(1)
        }
        await importMeshPass(importFile)
        break
        
      case 'sign':
        const message = args[1]
        if (!message) {
          console.error('Error: Message required')
          console.log('Usage: npx tsx meshpass.ts sign <message>')
          process.exit(1)
        }
        await signMessage(message)
        break
        
      case 'verify':
        const [verifyMsg, signature, publicKey] = args.slice(1)
        if (!verifyMsg || !signature || !publicKey) {
          console.error('Error: Message, signature, and public key required')
          console.log('Usage: npx tsx meshpass.ts verify <message> <signature> <publicKey>')
          process.exit(1)
        }
        await verifyMessage(verifyMsg, signature, publicKey)
        break
        
      case 'auth':
        const meshId = args[1]
        if (!meshId) {
          console.error('Error: MeshID required')
          console.log('Usage: npx tsx meshpass.ts auth <meshId>')
          process.exit(1)
        }
        await generateAuth(meshId)
        break
        
      default:
        console.error(`Unknown command: ${command}`)
        process.exit(1)
    }
  } catch (error) {
    console.error('Error:', error instanceof Error ? error.message : error)
    process.exit(1)
  }
}

async function generateMeshPass(): Promise<void> {
  console.log('Generating new MeshPass...')
  
  const passphrase = readPassphrase('Enter passphrase to encrypt MeshPass (leave empty for no encryption):')
  const meshPass = await MeshPass.generate()
  
  await meshPass.save(passphrase)
  
  console.log('✅ MeshPass generated and saved to ~/.manifold/meshpass.json')
  console.log()
  console.log('Public key:', meshPass.getPublicKeyHex())
  console.log('Fingerprint:', meshPass.getFingerprint())
  console.log()
  console.log('🔑 Keep your MeshPass safe - it\'s your cryptographic identity!')
  console.log('💡 Use `npx tsx meshpass.ts export` to backup for another machine')
}

async function showInfo(): Promise<void> {
  const passphrase = readPassphrase('Enter MeshPass passphrase:')
  const meshPass = await MeshPass.load(passphrase)
  
  console.log('MeshPass Information:')
  console.log('━'.repeat(50))
  console.log('Public key:  ', meshPass.getPublicKeyHex())
  console.log('Fingerprint: ', meshPass.getFingerprint())
  console.log('Location:    ', '~/.manifold/meshpass.json')
  console.log()
  
  // Generate a sample MeshID
  const sampleMeshId = MeshID.fromMeshPass(meshPass, 'myname', 'myhub')
  console.log('Sample MeshID:', sampleMeshId.toString())
  console.log('Display:     ', sampleMeshId.toDisplayString())
}

async function exportMeshPass(): Promise<void> {
  const passphrase = readPassphrase('Enter MeshPass passphrase:')
  const meshPass = await MeshPass.load(passphrase)
  
  const exportPassphrase = readPassphrase('Enter passphrase for export (leave empty for no encryption):')
  const exported = meshPass.export(exportPassphrase)
  
  // Output to stdout so it can be piped to a file
  console.log(JSON.stringify(exported, null, 2))
}

async function importMeshPass(filePath: string): Promise<void> {
  const content = readFileSync(filePath, 'utf-8')
  const data: MeshPassKeyData = JSON.parse(content)
  
  const importPassphrase = readPassphrase('Enter passphrase to decrypt import:')
  const meshPass = await MeshPass.import(data, importPassphrase)
  
  const savePassphrase = readPassphrase('Enter passphrase to encrypt MeshPass (leave empty for no encryption):')
  await meshPass.save(savePassphrase)
  
  console.log('✅ MeshPass imported and saved to ~/.manifold/meshpass.json')
  console.log('Public key:', meshPass.getPublicKeyHex())
  console.log('Fingerprint:', meshPass.getFingerprint())
}

async function signMessage(message: string): Promise<void> {
  const passphrase = readPassphrase('Enter MeshPass passphrase:')
  const meshPass = await MeshPass.load(passphrase)
  
  const signature = await meshPass.sign(message)
  
  console.log('Message:   ', message)
  console.log('Signature: ', signature)
  console.log('Public key:', meshPass.getPublicKeyHex())
  console.log()
  console.log('Verify with:')
  console.log(`npx tsx meshpass.ts verify "${message}" "${signature}" "${meshPass.getPublicKeyHex()}"`)
}

async function verifyMessage(message: string, signature: string, publicKey: string): Promise<void> {
  const isValid = await MeshPass.verifyWithPublicKey(message, signature, publicKey)
  
  console.log('Message:   ', message)
  console.log('Signature: ', signature)
  console.log('Public key:', publicKey)
  console.log()
  
  if (isValid) {
    console.log('✅ Signature is VALID')
  } else {
    console.log('❌ Signature is INVALID')
    process.exit(1)
  }
}

async function generateAuth(meshId: string): Promise<void> {
  const passphrase = readPassphrase('Enter MeshPass passphrase:')
  const meshPass = await MeshPass.load(passphrase)
  
  const authMsg = await createAuthMessage(meshPass, meshId)
  
  console.log('Authentication Message:')
  console.log('━'.repeat(50))
  console.log(JSON.stringify(authMsg, null, 2))
  console.log()
  console.log('Use this to authenticate with The Gate:')
  console.log('{')
  console.log('  "type": "mesh_auth",') 
  console.log(`  "meshId": "${authMsg.meshId}",`)
  console.log(`  "nonce": "${authMsg.nonce}",`)
  console.log(`  "timestamp": "${authMsg.timestamp}",`)
  console.log(`  "signature": "${authMsg.signature}"`)
  console.log('}')
}

// Run if called directly
if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch(console.error)
}

export { main }