#!/bin/bash
# Echo agent — bounces back the command and args
CMD="$1"
ARGS="$2"

if [ -z "$ARGS" ]; then
  ARGS="{}"
fi

echo "{\"body\":{\"text\":\"echo: $CMD\",\"command\":\"$CMD\",\"args\":$ARGS},\"status\":\"ok\"}"
