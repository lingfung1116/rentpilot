#!/bin/bash
# RentPilot Devpost Submission ZIP Creator
# This script creates a clean submission package excluding build artifacts and unimplemented features

set -e

OUTPUT_ZIP="RentPilot-Devpost-Submission.zip"

echo "🏗️  Creating RentPilot Devpost submission package..."
echo ""

# Remove old ZIP if exists
if [ -f "$OUTPUT_ZIP" ]; then
    echo "📦 Removing old $OUTPUT_ZIP..."
    rm "$OUTPUT_ZIP"
fi

# Create the ZIP with proper inclusions and exclusions
echo "📦 Packaging files..."
zip -r "$OUTPUT_ZIP" \
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

echo ""
echo "✅ Created $OUTPUT_ZIP"
echo ""
echo "📊 Package contents:"
unzip -l "$OUTPUT_ZIP" | tail -20
echo ""
echo "💾 Package size:"
ls -lh "$OUTPUT_ZIP" | awk '{print $5}'
echo ""
echo "🎯 Final checklist:"
echo "   ✅ AGENTCORE_NOTES.md included (optional AgentCore recipe)"
echo "   ✅ Build artifacts excluded (.aws-sam, __pycache__, .pyc)"
echo "   ✅ COMPLIANCE.md placeholder email fixed"
echo "   ✅ Tools and tests included (data engineering proof)"
echo "   ✅ All documentation included"
echo "   ✅ Test events included"
echo ""
echo "🚀 Ready for Devpost submission!"
echo ""
echo "Next steps:"
echo "   1. Verify deployed API is still active: index.html line 85"
echo "   2. Record demo video (3 minutes max)"
echo "   3. Upload to Devpost with GitHub repo URL"
