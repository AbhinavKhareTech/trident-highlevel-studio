#!/bin/bash
# Step 1: Create the repo on GitHub first (do this in browser or with gh CLI)
# Browser: https://github.com/new -> name: trident-consumption-graph, Public, no README
# OR with GitHub CLI:
gh repo create AbhinavKhareTech/trident-consumption-graph --public --description "Autonomous consumption agent: Three-prong ensemble (PyG + DGL + XGBoost) behavioral graph + multi-agent orchestration across Swiggy Food, Instamart, and Dineout MCP servers"

# Step 2: Initialize local repo
cd ~/trident-consumption-graph   # or wherever your project folder is
git init
git branch -M main

# Step 3: Add remote
git remote add origin git@github.com:AbhinavKhareTech/trident-consumption-graph.git

# Step 4: Create .gitignore before first commit
cat > .gitignore << 'EOF'
__pycache__/
*.py[cod]
*$py.class
*.egg-info/
dist/
build/
.eggs/
*.egg
.env
.venv/
venv/
env/
*.pkl
*.pt
*.pth
*.onnx
*.npy
.ipynb_checkpoints/
*.log
.DS_Store
.mypy_cache/
.ruff_cache/
.pytest_cache/
EOF

# Step 5: Stage all files
git add .

# Step 6: Initial commit
git commit -m "feat: BGI Trident scaffold - three-prong ensemble (PyG + DGL + XGBoost) for Swiggy MCP

- Trident = PyG structural embeddings + DGL temporal embeddings + XGBoost tabular features
- Ensemble meta-learner with stacked generalization and Platt calibration
- Repo structure: graph engine (three prongs), Trident orchestrator, 3 domain agents, mock MCP servers
- Architecture docs with Mermaid diagrams
- DoorDash GNN prior art comparison (single ID-GNN vs three-prong ensemble)
- Graph schema: 6 node types, 8 cross-domain edge types
- Voice provider abstraction layer (Vapi/Bolna/Retell swappable)
- Demo script for 2-min video walkthrough
- Mock-to-live MCP swap via config"

# Step 7: Push
git push -u origin main
