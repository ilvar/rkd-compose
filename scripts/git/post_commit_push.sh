#!/bin/sh
# Auto-push the current branch after each commit.
branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
if [ -n "$branch" ] && [ "$branch" != "HEAD" ]; then
  git push -u origin "$branch"
fi
