/**
 * Collect all variables available for webhook payload templates
 */

import { type FlowNode } from "@/components/flow/types";

export interface WebhookVariable {
  name: string; // e.g., "budget"
  displayName: string; // e.g., "Budget"
  path: string; // e.g., "gathered_context.budget"
  type?: string; // e.g., "number"
  source: string; // e.g., "Agent Node: Qualification"
  description?: string; // e.g., "Customer's monthly budget"
}

export interface VariableCategory {
  category: "extracted" | "initial_context" | "metadata" | "builtin";
  label: string;
  icon: string;
  variables: WebhookVariable[];
}

function toDisplayName(snakeCase: string): string {
  return snakeCase
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

export function collectWebhookVariables(nodes: FlowNode[]): VariableCategory[] {
  const categories: VariableCategory[] = [];

  // 1. EXTRACTED VARIABLES (from agent nodes) - PRIORITY
  const extractedVars: WebhookVariable[] = [];

  nodes.forEach((node) => {
    // Check if node has extraction enabled
    const nodeData = node.data as any;

    if (!nodeData?.extraction_enabled) {
      return;
    }

    const extractionVars = nodeData.extraction_variables || [];
    extractionVars.forEach((v: any) => {
      extractedVars.push({
        name: v.name,
        displayName: toDisplayName(v.name),
        path: `gathered_context.${v.name}`,
        type: v.type,
        source: `Agent Node: ${nodeData.name || node.id}`,
        description: v.prompt,
      });
    });
  });

  if (extractedVars.length > 0) {
    categories.push({
      category: "extracted",
      label: "Extracted Variables (from Agent Nodes)",
      icon: "🔄",
      variables: extractedVars,
    });
  }

  // 2. INITIAL CONTEXT (trigger data, campaign CSV)
  const initialContextVars: WebhookVariable[] = [
    {
      name: "initial_context",
      displayName: "Initial Context (All)",
      path: "initial_context",
      source: "Workflow Context",
      description:
        "All initial context data (API trigger, campaign CSV, pre-call fetch)",
    },
    // Add common fields as shortcuts
    {
      name: "phone_number",
      displayName: "Phone Number",
      path: "initial_context.phone_number",
      type: "string",
      source: "Campaign/Trigger",
      description: "Customer phone number",
    },
  ];

  categories.push({
    category: "initial_context",
    label: "Initial Context",
    icon: "🎯",
    variables: initialContextVars,
  });

  // 3. METADATA (workflow info, call details)
  const metadataVars: WebhookVariable[] = [
    {
      name: "workflow_run_id",
      displayName: "Workflow Run ID",
      path: "workflow_run_id",
      type: "string",
      source: "Workflow Metadata",
      description: "Unique identifier for this call",
    },
    {
      name: "workflow_name",
      displayName: "Workflow Name",
      path: "workflow_name",
      type: "string",
      source: "Workflow Metadata",
    },
    {
      name: "call_time",
      displayName: "Call Time",
      path: "call_time",
      type: "string",
      source: "Workflow Metadata",
      description: "ISO timestamp when call started",
    },
    {
      name: "gathered_context",
      displayName: "Gathered Context (All)",
      path: "gathered_context",
      source: "Workflow Context",
      description: "All extracted variables and conversation data",
    },
  ];

  categories.push({
    category: "metadata",
    label: "Workflow Metadata",
    icon: "📊",
    variables: metadataVars,
  });

  // 4. BUILT-IN (recording, transcript, QA)
  const builtinVars: WebhookVariable[] = [
    {
      name: "recording_url",
      displayName: "Recording URL",
      path: "recording_url",
      type: "string",
      source: "Call Artifacts",
      description: "URL to download call recording",
    },
    {
      name: "transcript_url",
      displayName: "Transcript URL",
      path: "transcript_url",
      type: "string",
      source: "Call Artifacts",
      description: "URL to download call transcript",
    },
    {
      name: "annotations",
      displayName: "QA Annotations",
      path: "annotations",
      source: "Quality Assurance",
      description: "QA analysis results (if enabled)",
    },
    {
      name: "cost_info",
      displayName: "Cost Information",
      path: "cost_info",
      source: "Usage Metrics",
      description: "Call cost and usage data",
    },
  ];

  categories.push({
    category: "builtin",
    label: "Built-in Variables",
    icon: "⚡",
    variables: builtinVars,
  });

  return categories;
}
