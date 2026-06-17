import { useState, useRef, useEffect, useMemo } from "react";
import { PlusIcon, Trash2Icon } from "lucide-react";
import { toast } from "sonner";

import type {
    DocumentResponseSchema,
    PropertySpec,
    RecordingResponseSchema,
    ToolResponse,
} from "@/client/types.gen";
import { DocumentSelector } from "@/components/flow/DocumentSelector";
import { MentionTextarea } from "@/components/flow/MentionTextarea";
import { RecordingSelect } from "@/components/flow/TextOrAudioInput";
import { ToolSelector } from "@/components/flow/ToolSelector";
import { WebhookVariablePicker } from "@/components/flow/webhook/VariablePicker";
import { CredentialSelector, UrlInput } from "@/components/http";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";

import { evaluateDisplayOptions } from "./displayOptions";

export interface RendererContext {
    tools: ToolResponse[];
    documents: DocumentResponseSchema[];
    recordings: RecordingResponseSchema[];
    /** Per-node MCP function allowlist (sibling of tool_uuids on node data). */
    mcpToolFilters?: Record<string, string[]>;
    /** Persist a new mcp_tool_filters object onto the node form values. */
    onMcpToolFiltersChange?: (next: Record<string, string[]>) => void;
}

export interface PropertyInputProps {
    spec: PropertySpec;
    value: unknown;
    onChange: (value: unknown) => void;
    context: RendererContext;
}

/**
 * Generic property dispatcher. Renders the right widget based on
 * `spec.type` and the standard label/description layout. Widgets that
 * already own their own label structure (Tool/DocumentSelector) are told
 * to suppress it via `showLabel={false}`.
 *
 * Caller is responsible for evaluating `display_options` — `PropertyInput`
 * always renders. NodeEditForm filters out hidden properties before
 * mounting them.
 */
export function PropertyInput({ spec, value, onChange, context }: PropertyInputProps) {
    switch (spec.type) {
        case "string":
            return <StringWidget spec={spec} value={value} onChange={onChange} />;
        case "number":
            return <NumberWidget spec={spec} value={value} onChange={onChange} />;
        case "boolean":
            return <BooleanWidget spec={spec} value={value} onChange={onChange} />;
        case "options":
            return <OptionsWidget spec={spec} value={value} onChange={onChange} />;
        case "multi_options":
            return <MultiOptionsWidget spec={spec} value={value} onChange={onChange} />;
        case "fixed_collection":
            return (
                <FixedCollectionWidget
                    spec={spec}
                    value={value}
                    onChange={onChange}
                    context={context}
                />
            );
        case "json":
            return <JsonWidget spec={spec} value={value} onChange={onChange} />;
        case "url":
            return <UrlWidget spec={spec} value={value} onChange={onChange} />;
        case "mention_textarea":
            return (
                <MentionWidget
                    spec={spec}
                    value={value}
                    onChange={onChange}
                    recordings={context.recordings}
                />
            );
        case "tool_refs":
            return (
                <ToolRefsWidget
                    spec={spec}
                    value={value}
                    onChange={onChange}
                    tools={context.tools}
                    mcpToolFilters={context.mcpToolFilters ?? {}}
                    onMcpToolFiltersChange={
                        context.onMcpToolFiltersChange ?? (() => {})
                    }
                />
            );
        case "document_refs":
            return (
                <DocumentRefsWidget
                    spec={spec}
                    value={value}
                    onChange={onChange}
                    documents={context.documents}
                />
            );
        case "recording_ref":
            return (
                <RecordingRefWidget
                    spec={spec}
                    value={value}
                    onChange={onChange}
                    recordings={context.recordings}
                />
            );
        case "credential_ref":
            return <CredentialRefWidget spec={spec} value={value} onChange={onChange} />;
        default: {
            const exhaustiveCheck: never = spec.type;
            return (
                <div className="text-xs text-destructive">
                    Unknown property type: {String(exhaustiveCheck)}
                </div>
            );
        }
    }
}

// ─── Layout helpers ──────────────────────────────────────────────────────

function StackedLabel({ spec }: { spec: PropertySpec }) {
    return (
        <>
            <Label>
                {spec.display_name}
                {spec.required && <span className="text-destructive ml-1">*</span>}
            </Label>
            {spec.description && (
                <Label className="text-xs text-muted-foreground">{spec.description}</Label>
            )}
        </>
    );
}

// ─── Widgets ─────────────────────────────────────────────────────────────

interface WidgetProps {
    spec: PropertySpec;
    value: unknown;
    onChange: (v: unknown) => void;
}

function StringWidget({ spec, value, onChange }: WidgetProps) {
    const v = (value as string | undefined) ?? "";
    const isMultiline = spec.editor === "textarea";
    return (
        <div className="grid gap-2">
            <StackedLabel spec={spec} />
            {isMultiline ? (
                <Textarea
                    value={v}
                    onChange={(e) => onChange(e.target.value)}
                    placeholder={spec.placeholder ?? undefined}
                    className="min-h-[80px] max-h-[200px] resize-none"
                    style={{ overflowY: "auto" }}
                />
            ) : (
                <Input
                    value={v}
                    onChange={(e) => onChange(e.target.value)}
                    placeholder={spec.placeholder ?? undefined}
                />
            )}
        </div>
    );
}

function NumberWidget({ spec, value, onChange }: WidgetProps) {
    const v = (value as number | undefined) ?? "";
    return (
        <div className="grid gap-2">
            <StackedLabel spec={spec} />
            <Input
                type="number"
                value={v as number | string}
                step={spec.min_value && spec.min_value < 1 ? 0.1 : 1}
                min={spec.min_value ?? undefined}
                max={spec.max_value ?? undefined}
                onChange={(e) => {
                    const next = e.target.value;
                    onChange(next === "" ? undefined : parseFloat(next));
                }}
                placeholder={spec.placeholder ?? undefined}
                className="w-32"
            />
        </div>
    );
}

function BooleanWidget({ spec, value, onChange }: WidgetProps) {
    const v = !!value;
    return (
        <div className="flex items-center space-x-2">
            <Switch id={`prop-${spec.name}`} checked={v} onCheckedChange={onChange} />
            <Label htmlFor={`prop-${spec.name}`}>{spec.display_name}</Label>
            {spec.description && (
                <Label className="text-xs text-muted-foreground ml-2">
                    {spec.description}
                </Label>
            )}
        </div>
    );
}

function OptionsWidget({ spec, value, onChange }: WidgetProps) {
    return (
        <div className="grid gap-2">
            <StackedLabel spec={spec} />
            <select
                className="border rounded-md p-2 text-sm bg-background"
                value={(value as string | number | undefined) ?? ""}
                onChange={(e) => {
                    const raw = e.target.value;
                    const opt = spec.options?.find((o) => String(o.value) === raw);
                    onChange(opt?.value ?? raw);
                }}
            >
                {spec.options?.map((o) => (
                    <option key={String(o.value)} value={String(o.value)}>
                        {o.label}
                    </option>
                ))}
            </select>
        </div>
    );
}

function MultiOptionsWidget({ spec, value, onChange }: WidgetProps) {
    const selected = new Set(((value as unknown[]) ?? []).map((v) => String(v)));
    return (
        <div className="grid gap-2">
            <StackedLabel spec={spec} />
            <div className="flex flex-col gap-1 border rounded-md p-2">
                {spec.options?.map((o) => {
                    const key = String(o.value);
                    return (
                        <label key={key} className="flex items-center gap-2 text-sm">
                            <input
                                type="checkbox"
                                checked={selected.has(key)}
                                onChange={(e) => {
                                    const next = new Set(selected);
                                    if (e.target.checked) next.add(key);
                                    else next.delete(key);
                                    onChange(
                                        spec.options
                                            ?.filter((opt) => next.has(String(opt.value)))
                                            .map((opt) => opt.value) ?? [],
                                    );
                                }}
                            />
                            {o.label}
                        </label>
                    );
                })}
            </div>
        </div>
    );
}

function FixedCollectionWidget({
    spec,
    value,
    onChange,
    context,
}: WidgetProps & { context: RendererContext }) {
    const rows = (value as Array<Record<string, unknown>> | undefined) ?? [];
    const subProps = spec.properties ?? [];

    const handleRowChange = (idx: number, propName: string, propValue: unknown) => {
        const next = rows.map((row, i) =>
            i === idx ? { ...row, [propName]: propValue } : row,
        );
        onChange(next);
    };

    const handleRemove = (idx: number) => {
        onChange(rows.filter((_, i) => i !== idx));
    };

    const handleAdd = () => {
        const blank: Record<string, unknown> = {};
        for (const p of subProps) blank[p.name] = p.default ?? undefined;
        onChange([...rows, blank]);
    };

    return (
        <div className="grid gap-2">
            <StackedLabel spec={spec} />
            <div className="space-y-2">
                {rows.map((row, idx) => (
                    <div key={idx} className="border rounded-md p-2 bg-background space-y-2">
                        <div className="flex items-start gap-2">
                            <div className="flex-1 space-y-2">
                                {subProps
                                    .filter((sub) =>
                                        evaluateDisplayOptions(sub.display_options, row),
                                    )
                                    .map((sub) => (
                                        <PropertyInput
                                            key={sub.name}
                                            spec={sub}
                                            value={row[sub.name]}
                                            onChange={(v) =>
                                                handleRowChange(idx, sub.name, v)
                                            }
                                            context={context}
                                        />
                                    ))}
                            </div>
                            <Button
                                variant="outline"
                                size="icon"
                                onClick={() => handleRemove(idx)}
                                aria-label={`Remove row ${idx + 1}`}
                            >
                                <Trash2Icon className="w-4 h-4" />
                            </Button>
                        </div>
                    </div>
                ))}
                <Button variant="outline" size="sm" className="w-fit" onClick={handleAdd}>
                    <PlusIcon className="w-4 h-4 mr-1" /> Add
                </Button>
            </div>
        </div>
    );
}

function JsonWidget({ spec, value, onChange }: WidgetProps) {
    const [pickerOpen, setPickerOpen] = useState(false);
    const [cursorPosition, setCursorPosition] = useState(0);
    const textareaRef = useRef<HTMLTextAreaElement>(null);

    // Track if user is actively editing to prevent value overwrite
    const isEditingRef = useRef(false);

    // Compute text representation from value (memoized)
    const text = useMemo(() => {
        if (value === undefined || value === null) return "";
        if (typeof value === "string") return value;
        try {
            return JSON.stringify(value, null, 2);
        } catch {
            return String(value);
        }
    }, [value]);

    // Maintain internal text state to allow editing invalid JSON
    const [internalText, setInternalText] = useState(text);
    const [jsonError, setJsonError] = useState<string | null>(null);

    // Sync internal text with incoming value changes (only when not editing)
    useEffect(() => {
        if (!isEditingRef.current) {
            setInternalText(text);
        }
    }, [text]);

    // For webhook payload_template, show variable picker
    const isWebhookPayload = spec.name === "payload_template";

    const handleTextChange = (raw: string) => {
        isEditingRef.current = true;
        setInternalText(raw);

        // Try to parse and propagate to parent
        if (raw === "") {
            setJsonError(null);
            onChange(undefined);
            return;
        }

        try {
            const parsed = JSON.parse(raw);
            setJsonError(null);
            onChange(parsed);
        } catch (e) {
            // Don't propagate invalid JSON to parent
            // Keep error state to show validation message
            setJsonError(e instanceof Error ? e.message : "Invalid JSON");
        }
    };

    const handleBlur = () => {
        // Clear editing flag when user leaves the field
        isEditingRef.current = false;
    };

    const handleInsertVariable = (variablePath: string) => {
        const variableText = `{{${variablePath}}}`;
        const textarea = textareaRef.current;

        if (!textarea) {
            // Fallback: just copy to clipboard
            navigator.clipboard.writeText(variableText);
            toast.info("Copied to clipboard - paste into payload");
            return;
        }

        // Get current text value
        const currentText = internalText;
        const start = textarea.selectionStart || cursorPosition;
        const end = textarea.selectionEnd || cursorPosition;

        // Insert variable at cursor position
        const newText = currentText.substring(0, start) + variableText + currentText.substring(end);

        // Update with the new text
        handleTextChange(newText);

        // Set cursor position after the inserted variable
        setTimeout(() => {
            if (textarea) {
                const newPosition = start + variableText.length;
                textarea.focus();
                textarea.setSelectionRange(newPosition, newPosition);
                setCursorPosition(newPosition);
            }
        }, 0);

        // Show success message
        toast.success(`Inserted {{${variablePath}}} into payload`);
    };

    return (
        <div className="grid gap-2">
            <div className="flex items-center justify-between">
                <StackedLabel spec={spec} />
                {isWebhookPayload && (
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setPickerOpen(true)}
                        type="button"
                    >
                        Browse Variables
                    </Button>
                )}
            </div>
            <Textarea
                ref={textareaRef}
                value={internalText}
                onChange={(e) => handleTextChange(e.target.value)}
                onBlur={handleBlur}
                onSelect={(e) => {
                    // Track cursor position when user clicks or selects
                    setCursorPosition(e.currentTarget.selectionStart);
                }}
                onClick={(e) => {
                    // Also track on click
                    setCursorPosition(e.currentTarget.selectionStart);
                }}
                placeholder={spec.placeholder ?? "{ }"}
                className="font-mono text-xs min-h-[120px]"
            />
            {jsonError && (
                <p className="text-xs text-destructive">
                    {jsonError}
                </p>
            )}
            {isWebhookPayload && (
                <>
                    <p className="text-xs text-muted-foreground">
                        Use <code>{"{{variable_path}}"}</code> syntax to insert variables.
                        Click &quot;Browse Variables&quot; to see available options.
                    </p>
                    <WebhookVariablePicker
                        open={pickerOpen}
                        onOpenChange={setPickerOpen}
                        onSelectVariable={handleInsertVariable}
                    />
                </>
            )}
        </div>
    );
}

function UrlWidget({ spec, value, onChange }: WidgetProps) {
    return (
        <div className="grid gap-2">
            <StackedLabel spec={spec} />
            <UrlInput
                value={(value as string | undefined) ?? ""}
                onChange={onChange}
                placeholder={spec.placeholder ?? undefined}
                showValidation
            />
        </div>
    );
}

function MentionWidget({
    spec,
    value,
    onChange,
    recordings,
}: WidgetProps & { recordings: RecordingResponseSchema[] }) {
    return (
        <div className="grid gap-2">
            <StackedLabel spec={spec} />
            <MentionTextarea
                value={(value as string | undefined) ?? ""}
                onChange={onChange}
                placeholder={spec.placeholder ?? undefined}
                className="min-h-[100px] max-h-[300px] resize-none overflow-y-auto"
                recordings={recordings}
            />
        </div>
    );
}

function ToolRefsWidget({
    spec,
    value,
    onChange,
    tools,
    mcpToolFilters,
    onMcpToolFiltersChange,
}: WidgetProps & {
    tools: ToolResponse[];
    mcpToolFilters: Record<string, string[]>;
    onMcpToolFiltersChange: (next: Record<string, string[]>) => void;
}) {
    return (
        <ToolSelector
            value={(value as string[] | undefined) ?? []}
            onChange={onChange}
            tools={tools}
            label={spec.display_name}
            description={spec.description}
            mcpToolFilters={mcpToolFilters}
            onMcpToolFiltersChange={onMcpToolFiltersChange}
        />
    );
}

function DocumentRefsWidget({
    spec,
    value,
    onChange,
    documents,
}: WidgetProps & { documents: DocumentResponseSchema[] }) {
    return (
        <DocumentSelector
            value={(value as string[] | undefined) ?? []}
            onChange={onChange}
            documents={documents}
            label={spec.display_name}
            description={spec.description}
        />
    );
}

function RecordingRefWidget({
    spec,
    value,
    onChange,
    recordings,
}: WidgetProps & { recordings: RecordingResponseSchema[] }) {
    return (
        <div className="grid gap-2">
            <StackedLabel spec={spec} />
            <RecordingSelect
                value={(value as string | undefined) ?? ""}
                onChange={onChange}
                recordings={recordings}
            />
        </div>
    );
}

function CredentialRefWidget({ spec, value, onChange }: WidgetProps) {
    return (
        <div className="grid gap-2">
            <StackedLabel spec={spec} />
            <CredentialSelector
                value={(value as string | undefined) ?? ""}
                onChange={onChange}
                showLabel={false}
            />
        </div>
    );
}
