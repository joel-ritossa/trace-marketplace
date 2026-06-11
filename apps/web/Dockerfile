# Build context is the repo root (pnpm workspace).

# Snapshot of the tracked repo tree for the /ask code agent. Exported from
# .git alone (git archive needs no worktree), so the snapshot is pinned to
# the HEAD commit being built and .gitignored junk can never leak in.
FROM alpine/git:latest AS snapshot
COPY .git /src/.git
WORKDIR /src
RUN mkdir -p /snapshot \
  && git archive HEAD | tar -x -C /snapshot \
  && git ls-tree -r HEAD --name-only > /snapshot/.manifest

FROM node:22-alpine

RUN corepack enable
WORKDIR /repo

COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY apps/web/package.json apps/web/
RUN pnpm install --frozen-lockfile --filter web

COPY apps/web apps/web

ARG NEXT_PUBLIC_SUPABASE_URL
ARG NEXT_PUBLIC_SUPABASE_ANON_KEY
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_UPLOAD_MAX_FILES
ENV NEXT_PUBLIC_SUPABASE_URL=$NEXT_PUBLIC_SUPABASE_URL \
    NEXT_PUBLIC_SUPABASE_ANON_KEY=$NEXT_PUBLIC_SUPABASE_ANON_KEY \
    NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_UPLOAD_MAX_FILES=$NEXT_PUBLIC_UPLOAD_MAX_FILES

RUN pnpm --filter web build

COPY --from=snapshot /snapshot /repo-snapshot
ENV REPO_SNAPSHOT_DIR=/repo-snapshot

EXPOSE 3000
CMD ["pnpm", "--filter", "web", "start"]
