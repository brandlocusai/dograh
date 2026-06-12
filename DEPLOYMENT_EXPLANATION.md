# Docker Deployment Explanation

## 🎯 The Problem You Discovered

```bash
# What we were doing (WRONG)
docker compose restart api ui

# Result:
✅ Containers restart
❌ Still running OLD Docker images
❌ Code changes NOT deployed
```

**Why?** `docker restart` only restarts existing containers. It doesn't:
- Rebuild images with new code
- Pick up changes from your codebase
- Update the running application

## ✅ The Correct Solution

```bash
# Step 1: Rebuild images with new code
docker compose build api ui

# Step 2: Recreate containers with new images
docker compose up -d --no-deps --force-recreate api ui
```

### What Each Flag Does:

- **`build`** - Rebuilds Docker images from Dockerfiles with latest code
- **`up -d`** - Start containers in detached mode
- **`--no-deps`** - Don't recreate dependencies (postgres, redis stay running)
- **`--force-recreate`** - Force recreation even if config unchanged
- **`api ui`** - Only recreate these services (not postgres, redis, minio)

## 📊 Comparison

### Old Deployment (Restart Only)
```
1. docker compose restart api    → Restart container
2. docker compose restart ui     → Restart container
   ↓
Result: Same old images, code unchanged ❌
Time: 10 seconds
Downtime: Minimal
```

### New Deployment (Rebuild + Recreate)
```
1. docker compose build api ui              → Rebuild with new code
2. docker compose up -d --no-deps api ui   → Recreate containers
   ↓
Result: New images with latest code ✅
Time: 2-5 minutes (build time)
Downtime: 10-30 seconds (container recreation)
```

## 🚀 Optimizations We Added

### 1. Docker BuildKit
```bash
export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1
```
- Faster builds with layer caching
- Parallel build steps
- Better build performance

### 2. Selective Rebuild
```bash
# Only rebuild changed services
docker compose build api ui

# NOT all services
docker compose build  # ❌ Would rebuild postgres, redis, etc.
```
- Faster deployment (only app containers)
- Database/cache stay running (no data issues)
- Less downtime

### 3. No-Deps Flag
```bash
--no-deps
```
- Prevents cascading restarts
- postgres, redis, minio keep running
- Only api and ui are recreated

## 📋 Full Deployment Flow

```
1. SSH to VM
2. cd /root/dograh-live/dograh
3. git pull origin main
4. git submodule update
5. docker compose exec api alembic upgrade head  # Migrations
6. docker compose build api ui                   # Rebuild images
7. docker compose up -d --no-deps --force-recreate api ui  # Recreate
8. docker compose exec nginx nginx -s reload     # Reload nginx
9. Health checks
```

## ⏱️ Deployment Timeline

| Phase | Duration | What Happens |
|-------|----------|--------------|
| Git pull | 10s | Download latest code |
| Submodule update | 5s | Update pipecat |
| Database migrations | 5-30s | Update DB schema |
| **Build images** | **2-5 min** | Rebuild Docker images |
| Recreate containers | 30s | Create new containers |
| Nginx reload | 1s | Update routing |
| Health checks | 30s | Verify deployment |
| **Total** | **3-7 min** | Complete deployment |

## 🔍 Why Build Time Varies

Build time depends on:

1. **Code changes**
   - Small change: 1-2 min (cached layers)
   - Large change: 3-5 min (rebuild layers)

2. **Dependencies**
   - No dependency change: Fast (cached)
   - npm/pip install needed: Slower

3. **Docker cache**
   - Warm cache: Fast
   - Cold cache: Slow

4. **Server resources**
   - Good CPU: Fast builds
   - Limited CPU: Slower builds

## 🎯 What Gets Rebuilt

### API Container (`api/Dockerfile`)
```dockerfile
FROM python:3.13
# Install system dependencies
# Copy requirements
# Install Python packages
# Copy application code  ← Your changes here
# Start uvicorn
```
**Cached:** System deps, Python packages (if requirements.txt unchanged)
**Rebuilt:** Application code (your API changes)

### UI Container (`ui/Dockerfile`)
```dockerfile
FROM node:22
# Install system dependencies
# Copy package.json
# npm install
# Copy application code  ← Your changes here
# Build Next.js app
# Start Next.js
```
**Cached:** node_modules (if package.json unchanged)
**Rebuilt:** Application code + Next.js build (your UI changes)

## 💡 Why This is Better

### Before (Restart Only)
```
Push code → Restart containers → Code unchanged ❌
User sees: Old version
Time: 10 seconds
Effectiveness: 0% (doesn't work)
```

### After (Rebuild + Recreate)
```
Push code → Build images → Recreate containers → Code updated ✅
User sees: New version
Time: 3-7 minutes
Effectiveness: 100% (works correctly)
```

## 🔒 Safety Features

### 1. Database Safety
```bash
# We DON'T recreate postgres
docker compose up -d --no-deps api ui

# NOT this (would lose data!)
docker compose up -d  # ❌
```

### 2. Zero-Downtime for Database
- postgres keeps running during deployment
- redis keeps running during deployment
- minio keeps running during deployment
- Only api and ui are recreated

### 3. Build Failure Safety
```bash
if ! docker compose build api ui; then
    error_exit "Build failed - old containers still running"
fi
```
If build fails, old containers keep serving traffic

### 4. Health Check Validation
After deployment, we verify:
- Health endpoint returns 200
- All containers are running
- No restart loops
- No critical errors in logs

## 🆚 Alternative Approaches

### Option 1: Full Rebuild (Simple but Slow)
```bash
docker compose build
docker compose up -d
```
**Pros:** Simple, ensures everything is fresh
**Cons:** Rebuilds postgres, redis (unnecessary, slower)

### Option 2: Restart Only (Fast but Wrong)
```bash
docker compose restart api ui
```
**Pros:** Very fast
**Cons:** Code doesn't update (doesn't work!)

### Option 3: Selective Rebuild (Best - What We Use)
```bash
docker compose build api ui
docker compose up -d --no-deps --force-recreate api ui
```
**Pros:** Fast, safe, actually works
**Cons:** None (this is the right way)

### Option 4: Blue-Green Deployment (Advanced)
Run two sets of containers, switch traffic
**Pros:** True zero-downtime
**Cons:** Complex, uses 2x resources

## 📝 Summary

**Your observation was 100% correct!** 🎯

- ❌ Restart doesn't rebuild images
- ✅ Build + recreate updates code properly
- ⏱️ Takes 3-7 minutes (build time)
- 🔒 Safe (database keeps running)
- 💯 Actually works (code updates)

## 🚀 Next Steps

```bash
# Commit the fix
git add scripts/ci_deploy_docker.sh
git commit -m "fix: rebuild Docker images to deploy code changes"

# Push and deploy
git push origin main

# Watch it work!
# - Build takes 2-5 minutes
# - Code actually updates this time ✅
```

---

**Key Takeaway:** Docker containers run **images**, not code. To deploy code changes, you must **rebuild images** and **recreate containers**. Simple restart won't cut it! 🐳
