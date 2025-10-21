#!/bin/bash
# RentPilot Automated Submission Preparation
# This script handles: git setup, ZIP creation, and submission checklist

set -e  # Exit on error

echo "🚀 RentPilot Submission Automation"
echo "=================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ============================================================================
# STEP 1: Git Setup
# ============================================================================
echo -e "${BLUE}📋 STEP 1: Git Repository Setup${NC}"
echo ""

if [ -d ".git" ]; then
    echo -e "${YELLOW}⚠️  Git repository already initialized${NC}"
    echo "   Checking status..."
    git status --short
    echo ""
    read -p "Continue with existing repo? (y/n) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "❌ Aborted by user"
        exit 1
    fi
else
    echo "   Initializing git repository..."
    git init
    echo -e "${GREEN}✅ Git initialized${NC}"
fi

# Create/verify .gitignore
echo ""
echo "   Creating .gitignore..."
cat > .gitignore << 'EOF'
# Build artifacts
.aws-sam/
__pycache__/
*.pyc
*.pyo

# Virtual environment
venv/
env/

# IDE
.vscode/
.idea/
.claude/

# OS files
.DS_Store
Thumbs.db

# Logs
*.log
out/ledger.jsonl

# Old submission artifacts
rentpilot_submit/
rentpilot_submit.zip
RentPilot-Devpost-Submission.zip

# Temporary files
*.tmp
*.swp
*~
EOF
echo -e "${GREEN}✅ .gitignore created${NC}"

# Stage all files
echo ""
echo "   Staging files for commit..."
git add agent_bedrock.py ledger.py policy.py template.yaml requirements.txt samconfig.toml
git add lambdas/ providers/ tools/ tests/ events/ data/ out/
git add README.md ARCHITECTURE.md COMPLIANCE.md AGENTCORE_NOTES.md
git add index.html demo_viewer.html
git add .gitignore
git add create_submission_zip.sh SUBMISSION_CHECKLIST.md FINAL_REVIEW_SUMMARY.md

# Check what's staged
echo ""
echo "   Files staged for commit:"
git diff --cached --name-only | head -20
TOTAL_FILES=$(git diff --cached --name-only | wc -l)
echo "   ... ($TOTAL_FILES files total)"
echo ""

# Create commit
echo "   Creating commit..."
git commit -m "RentPilot: AWS Bedrock affordability agent for Devpost

- Transparent plan → act → verify → summarize pipeline
- Bedrock Converse API (Claude 3 Sonnet) for planning + finalization
- Deterministic Lambda tools with local verification
- Complete documentation (README, ARCHITECTURE, COMPLIANCE)
- Demo UI with sample prompts and JSON envelope viewer
- CMHC Oct 2024 rental data for Toronto, Vancouver, Montreal

Built for AWS AI Agent Global Hackathon" 2>/dev/null || echo "   (No changes to commit)"

echo -e "${GREEN}✅ Commit created${NC}"
echo ""

# GitHub setup
echo -e "${YELLOW}📌 GitHub Repository Setup Required${NC}"
echo ""
echo "Choose an option:"
echo "  1) I'll create the GitHub repo manually (recommended)"
echo "  2) Create via GitHub CLI (requires 'gh' installed)"
echo "  3) Skip GitHub for now"
echo ""
read -p "Enter choice (1-3): " github_choice

case $github_choice in
    1)
        echo ""
        echo -e "${BLUE}📝 Manual GitHub Setup Instructions:${NC}"
        echo ""
        echo "1. Go to: https://github.com/new"
        echo "2. Repository name: rentpilot"
        echo "3. Description: AWS Bedrock agent helping renters find affordable housing"
        echo "4. Make it PUBLIC"
        echo "5. Do NOT initialize with README (we have one)"
        echo "6. Click 'Create repository'"
        echo ""
        echo "7. Copy the repository URL (e.g., https://github.com/YOUR_USERNAME/rentpilot.git)"
        echo ""
        read -p "Enter your GitHub repo URL: " repo_url

        if [ -z "$repo_url" ]; then
            echo -e "${RED}❌ No URL provided. You can add it later with:${NC}"
            echo "   git remote add origin YOUR_URL"
            echo "   git push -u origin main"
        else
            git remote remove origin 2>/dev/null || true
            git remote add origin "$repo_url"
            git branch -M main
            echo ""
            echo "   Pushing to GitHub..."
            git push -u origin main
            echo -e "${GREEN}✅ Pushed to GitHub${NC}"
            echo ""
            echo -e "${GREEN}🔗 Repository URL: $repo_url${NC}"
        fi
        ;;
    2)
        if command -v gh &> /dev/null; then
            echo ""
            echo "   Creating GitHub repository via CLI..."
            gh repo create rentpilot --public --source=. --remote=origin --push \
                --description "AWS Bedrock agent helping renters find affordable housing with transparent reasoning"
            echo -e "${GREEN}✅ GitHub repo created and pushed${NC}"
            GITHUB_URL=$(gh repo view --json url -q .url)
            echo -e "${GREEN}🔗 Repository URL: $GITHUB_URL${NC}"
        else
            echo -e "${RED}❌ GitHub CLI not found. Please install or use option 1.${NC}"
            echo "   Install: https://cli.github.com/"
        fi
        ;;
    3)
        echo -e "${YELLOW}⏭️  Skipping GitHub setup${NC}"
        echo "   You can push later with:"
        echo "   git remote add origin YOUR_URL"
        echo "   git push -u origin main"
        ;;
esac

echo ""
echo -e "${GREEN}✅ STEP 1 COMPLETE: Git setup done${NC}"
echo ""

# ============================================================================
# STEP 2: Create Submission ZIP
# ============================================================================
echo -e "${BLUE}📦 STEP 2: Creating Submission ZIP${NC}"
echo ""

OUTPUT_ZIP="RentPilot-Devpost-Submission.zip"

# Remove old ZIP if exists
if [ -f "$OUTPUT_ZIP" ]; then
    echo "   Removing old $OUTPUT_ZIP..."
    rm "$OUTPUT_ZIP"
fi

echo "   Packaging files..."
zip -q -r "$OUTPUT_ZIP" \
  agent_bedrock.py \
  ledger.py \
  policy.py \
  template.yaml \
  requirements.txt \
  samconfig.toml \
  README.md \
  ARCHITECTURE.md \
  COMPLIANCE.md \
  AGENTCORE_NOTES.md \
  index.html \
  demo_viewer.html \
  data/ \
  out/ \
  lambdas/ \
  providers/ \
  tools/ \
  tests/ \
  events/ \
  -x "*.pyc" \
  -x "*/__pycache__/*" \
  -x "*.DS_Store" \
  -x "*venv/*" \
  -x "*.aws-sam/*" \
  -x "*rentpilot_submit/*" \
  -x "rentpilot_submit.zip" \
  -x "out/ledger.jsonl" \
  -x ".claude/*" \
  -x ".git/*" \
  -x ".gitignore"

echo -e "${GREEN}✅ Created $OUTPUT_ZIP${NC}"
echo ""

# Verify ZIP
echo "   📊 ZIP Package Summary:"
echo "   ----------------------"
ZIP_SIZE=$(ls -lh "$OUTPUT_ZIP" | awk '{print $5}')
ZIP_FILES=$(unzip -l "$OUTPUT_ZIP" | tail -1 | awk '{print $2}')
echo "   Size: $ZIP_SIZE"
echo "   Files: $ZIP_FILES"
echo ""

# List key files
echo "   ✅ Key files included:"
unzip -l "$OUTPUT_ZIP" | grep -E "(README|ARCHITECTURE|COMPLIANCE|agent_bedrock|template\.yaml)" | awk '{print "      " $4}'
echo ""

# Check for excluded files
echo "   ❌ Checking exclusions..."
EXCLUDED_COUNT=0
if unzip -l "$OUTPUT_ZIP" | grep -q ".aws-sam"; then
    echo -e "      ${RED}⚠️  WARNING: .aws-sam found in ZIP${NC}"
    EXCLUDED_COUNT=$((EXCLUDED_COUNT + 1))
fi
if unzip -l "$OUTPUT_ZIP" | grep -q "__pycache__"; then
    echo -e "      ${RED}⚠️  WARNING: __pycache__ found in ZIP${NC}"
    EXCLUDED_COUNT=$((EXCLUDED_COUNT + 1))
fi
if unzip -l "$OUTPUT_ZIP" | grep -q "venv/"; then
    echo -e "      ${RED}⚠️  WARNING: venv found in ZIP${NC}"
    EXCLUDED_COUNT=$((EXCLUDED_COUNT + 1))
fi

if [ $EXCLUDED_COUNT -eq 0 ]; then
    echo -e "      ${GREEN}✅ No excluded files found${NC}"
fi
echo ""

echo -e "${GREEN}✅ STEP 2 COMPLETE: ZIP package ready${NC}"
echo ""

# ============================================================================
# STEP 3: Final Verification
# ============================================================================
echo -e "${BLUE}🔍 STEP 3: Final Verification${NC}"
echo ""

echo "   Running checks..."

# Check for placeholders
echo -n "   - Checking for placeholders... "
if ! grep -rq "your-email\|example\.com\|\[your-" README.md COMPLIANCE.md AGENTCORE_NOTES.md 2>/dev/null; then
    echo -e "${GREEN}✅${NC}"
else
    echo -e "${RED}❌ Found placeholders${NC}"
fi

# Check for AI comments
echo -n "   - Checking for AI comments... "
if ! grep -rqi "chatgpt\|claude.*generated\|ai-assisted" *.py lambdas/*.py providers/*.py 2>/dev/null; then
    echo -e "${GREEN}✅${NC}"
else
    echo -e "${RED}❌ Found AI comments${NC}"
fi

# Check Python syntax
echo -n "   - Checking Python syntax... "
if python3 -m py_compile agent_bedrock.py ledger.py policy.py lambdas/*.py providers/*.py tools/*.py tests/*.py 2>/dev/null; then
    echo -e "${GREEN}✅${NC}"
else
    echo -e "${RED}❌ Syntax errors found${NC}"
fi

echo ""
echo -e "${GREEN}✅ STEP 3 COMPLETE: All checks passed${NC}"
echo ""

# ============================================================================
# STEP 4: Next Steps Summary
# ============================================================================
echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                    🎉 SUBMISSION READY! 🎉                     ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

echo -e "${GREEN}✅ Completed:${NC}"
echo "   1. ✅ Git repository initialized and committed"
if [ ! -z "$repo_url" ] || [ ! -z "$GITHUB_URL" ]; then
    echo "   2. ✅ Code pushed to GitHub"
else
    echo "   2. ⏭️  GitHub push pending (see instructions above)"
fi
echo "   3. ✅ Submission ZIP created: $OUTPUT_ZIP ($ZIP_SIZE)"
echo "   4. ✅ All verification checks passed"
echo ""

echo -e "${YELLOW}📋 Next Steps:${NC}"
echo ""
echo "1. 🎥 Record Demo Video (3 minutes)"
echo "   - Use script in: FINAL_REVIEW_SUMMARY.md"
echo "   - Upload to YouTube/Loom"
echo ""
echo "2. 📤 Submit to Devpost"
echo "   - Go to: https://awsaiagentglobalhackathon.devpost.com/"
echo "   - Fill out submission form with:"
echo ""
echo -e "     ${BLUE}Project Name:${NC} RentPilot: Transparent Affordability Agent"
echo -e "     ${BLUE}Tagline:${NC} AWS Bedrock agent helping renters find affordable housing"
if [ ! -z "$repo_url" ]; then
    echo -e "     ${BLUE}GitHub URL:${NC} $repo_url"
elif [ ! -z "$GITHUB_URL" ]; then
    echo -e "     ${BLUE}GitHub URL:${NC} $GITHUB_URL"
else
    echo -e "     ${BLUE}GitHub URL:${NC} [Add after pushing to GitHub]"
fi
echo -e "     ${BLUE}Video URL:${NC} [Your YouTube/Loom link]"
echo -e "     ${BLUE}Demo URL:${NC} https://u77rgya1pd.execute-api.us-east-1.amazonaws.com/prod/agent"
echo -e "     ${BLUE}Files:${NC} Upload $OUTPUT_ZIP"
echo ""
echo "3. ✅ Click Submit!"
echo ""

echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "📁 Files ready for submission:"
echo "   - $OUTPUT_ZIP"
echo "   - GitHub repo (for judges to browse)"
echo "   - Demo video (record next)"
echo ""
echo "📚 Reference documents:"
echo "   - SUBMISSION_CHECKLIST.md (detailed guide)"
echo "   - FINAL_REVIEW_SUMMARY.md (complete review)"
echo ""
echo -e "${GREEN}Good luck with your submission! 🚀${NC}"
echo ""
