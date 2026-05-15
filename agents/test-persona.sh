#!/bin/bash
# Test script for persona-primed stella agent
# GROQ_API_KEY inherited from environment

PAYLOAD='{"origin":"mamasan@satelliteA#b200244f","body":{"text":"Hey Stella, quick test from the mesh. Can you tell me something only you would say? What do you actually think about running on satelliteA with your crew?"}}'

echo "$PAYLOAD" | python3 /home/stella/projects/Manifold/agents/stella-agent.py envelope_v1 --stdin
