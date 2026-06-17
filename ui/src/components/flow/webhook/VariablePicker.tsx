"use client";

import { useState, useMemo } from "react";
import { Copy, ChevronDown } from "lucide-react";
import { useNodes } from "@xyflow/react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { toast } from "sonner";
import type { FlowNode } from "@/components/flow/types";
import {
  collectWebhookVariables,
  type WebhookVariable,
  type VariableCategory,
} from "./collectWebhookVariables";

export function WebhookVariablePicker({
  open,
  onOpenChange,
  onSelectVariable,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSelectVariable: (variablePath: string) => void;
}) {
  const nodes = useNodes<FlowNode>();
  const [searchQuery, setSearchQuery] = useState("");

  // Collect variables from workflow
  const variables = useMemo(() => collectWebhookVariables(nodes), [nodes]);

  // Filter by search
  const filteredCategories = useMemo(() => {
    if (!searchQuery) return variables;

    const query = searchQuery.toLowerCase();
    return variables
      .map((cat) => ({
        ...cat,
        variables: cat.variables.filter(
          (v) =>
            v.name.toLowerCase().includes(query) ||
            v.displayName.toLowerCase().includes(query) ||
            v.path.toLowerCase().includes(query)
        ),
      }))
      .filter((cat) => cat.variables.length > 0);
  }, [variables, searchQuery]);

  const handleCopy = (variablePath: string) => {
    navigator.clipboard.writeText(`{{${variablePath}}}`);
    toast.success(`Copied {{${variablePath}}} to clipboard`);
  };

  const handleInsert = (variablePath: string) => {
    onSelectVariable(variablePath);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[80vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle>Available Variables for Webhook Payload</DialogTitle>
          <DialogDescription>
            Select variables from agent nodes and context to include in your
            webhook payload
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 flex-1 overflow-hidden flex flex-col">
          <Input
            placeholder="Search variables..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full"
          />

          <div className="flex-1 overflow-y-auto pr-2">
            <div className="space-y-4">
              {filteredCategories.map((category) => (
                <Collapsible key={category.category} defaultOpen>
                  <CollapsibleTrigger className="flex items-center gap-2 w-full p-2 hover:bg-accent rounded">
                    <span className="text-lg">{category.icon}</span>
                    <span className="font-semibold">{category.label}</span>
                    <Badge variant="secondary" className="ml-auto">
                      {category.variables.length}
                    </Badge>
                    <ChevronDown className="h-4 w-4" />
                  </CollapsibleTrigger>

                  <CollapsibleContent className="mt-2 space-y-2">
                    {category.variables.map((variable) => (
                      <Card key={variable.path} className="p-3">
                        <div className="space-y-2">
                          <div className="flex items-start justify-between">
                            <div className="flex-1">
                              <div className="flex items-center gap-2">
                                <code className="text-sm font-semibold">
                                  {variable.displayName}
                                </code>
                                {variable.type && (
                                  <Badge variant="outline" className="text-xs">
                                    {variable.type}
                                  </Badge>
                                )}
                              </div>

                              <p className="text-xs text-muted-foreground mt-1">
                                {variable.source}
                              </p>

                              {variable.description && (
                                <p className="text-sm text-muted-foreground mt-1">
                                  {variable.description}
                                </p>
                              )}

                              <code className="text-xs bg-muted px-2 py-1 rounded mt-2 inline-block">
                                {`{{${variable.path}}}`}
                              </code>
                            </div>
                          </div>

                          <div className="flex gap-2">
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => handleCopy(variable.path)}
                            >
                              <Copy className="h-3 w-3 mr-1" />
                              Copy
                            </Button>
                            <Button
                              size="sm"
                              onClick={() => handleInsert(variable.path)}
                            >
                              Insert into Payload
                            </Button>
                          </div>
                        </div>
                      </Card>
                    ))}
                  </CollapsibleContent>
                </Collapsible>
              ))}

              {filteredCategories.length === 0 && (
                <div className="text-center py-8 text-muted-foreground">
                  No variables found matching &quot;{searchQuery}&quot;
                </div>
              )}
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
