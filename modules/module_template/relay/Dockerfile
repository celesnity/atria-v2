FROM node:22-slim

WORKDIR /embinder
COPY minderSDK/package.json minderSDK/package-lock.json ./
COPY minderSDK/packages ./packages
RUN npm ci --ignore-scripts

ENV EMBINDER_ENABLE_MCP=false
ENV EMBINDER_ENABLE_CHAT=false
ENV EMBINDER_POLICY_PATH=/module/embinder.policy.json
ENV EMBINDER_AUDIT_PATH=/data/audit.jsonl

EXPOSE 7331
CMD ["npm", "--workspace", "@embinder/relay", "run", "start"]
