"use client";

import { Loader2, Pencil, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import {
    deleteCredentialApiV1CredentialsCredentialUuidDelete,
    listCredentialsApiV1CredentialsGet,
} from "@/client";
import { CredentialResponse } from "@/client/types.gen";
import { CreateCredentialDialog } from "@/components/http/create-credential-dialog";
import { Button } from "@/components/ui/button";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import { detailFromError } from "@/lib/apiError";
import { useAuth } from "@/lib/auth";

export function CredentialManagement() {
    const { user, loading: authLoading } = useAuth();
    const [credentials, setCredentials] = useState<CredentialResponse[]>([]);
    const [loading, setLoading] = useState(false);
    const [isAddDialogOpen, setIsAddDialogOpen] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [deletingUuid, setDeletingUuid] = useState<string | null>(null);

    const fetchCredentials = useCallback(async () => {
        if (authLoading || !user) return;

        setLoading(true);
        setError(null);
        try {
            const response = await listCredentialsApiV1CredentialsGet({});
            if (response.error) {
                setError(detailFromError(response.error, "Failed to fetch credentials"));
                setCredentials([]);
                return;
            }
            if (response.data) {
                setCredentials(response.data);
            }
        } catch (err) {
            setError("Failed to fetch credentials");
            setCredentials([]);
        } finally {
            setLoading(false);
        }
    }, [authLoading, user]);

    useEffect(() => {
        fetchCredentials();
    }, [fetchCredentials]);

    const handleDelete = async (uuid: string, name: string) => {
        if (!confirm(`Are you sure you want to delete credential "${name}"?`)) {
            return;
        }

        setDeletingUuid(uuid);
        setError(null);
        try {
            const response = await deleteCredentialApiV1CredentialsCredentialUuidDelete({
                path: { credential_uuid: uuid },
            });

            if (response.error) {
                setError(detailFromError(response.error, "Failed to delete credential"));
                return;
            }

            await fetchCredentials();
        } catch (err) {
            setError("Failed to delete credential");
        } finally {
            setDeletingUuid(null);
        }
    };

    const handleCredentialCreated = async () => {
        await fetchCredentials();
    };

    const getCredentialTypeName = (type: string) => {
        const typeMap: Record<string, string> = {
            bearer_token: "Bearer Token",
            api_key: "API Key",
            basic_auth: "Basic Auth",
        };
        return typeMap[type] || type;
    };

    if (loading && credentials.length === 0) {
        return (
            <div className="flex items-center justify-center p-8">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
        );
    }

    return (
        <div className="space-y-4">
            {error && (
                <div className="p-3 bg-destructive/10 border border-destructive/20 rounded-lg text-destructive text-sm">
                    {error}
                </div>
            )}

            <div className="flex justify-between items-center">
                <p className="text-sm text-muted-foreground">
                    Manage credentials used for HTTP API and MCP tool authentication.
                </p>
                <Button onClick={() => setIsAddDialogOpen(true)}>
                    Add Credential
                </Button>
            </div>

            {credentials.length === 0 ? (
                <div className="p-8 border rounded-lg bg-muted/20 text-center">
                    <p className="text-sm text-muted-foreground">
                        No credentials found. Click "Add Credential" to create one.
                    </p>
                </div>
            ) : (
                <div className="border rounded-lg">
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead>Name</TableHead>
                                <TableHead>Type</TableHead>
                                <TableHead>Created</TableHead>
                                <TableHead className="w-[100px]">Actions</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {credentials.map((credential) => (
                                <TableRow key={credential.uuid}>
                                    <TableCell className="font-medium">
                                        {credential.name}
                                    </TableCell>
                                    <TableCell>
                                        {getCredentialTypeName(credential.credential_type)}
                                    </TableCell>
                                    <TableCell className="text-muted-foreground">
                                        {new Date(credential.created_at).toLocaleDateString()}
                                    </TableCell>
                                    <TableCell>
                                        <div className="flex items-center gap-2">
                                            <Button
                                                variant="ghost"
                                                size="icon"
                                                onClick={() => handleDelete(credential.uuid, credential.name)}
                                                disabled={deletingUuid === credential.uuid}
                                                title="Delete credential"
                                            >
                                                {deletingUuid === credential.uuid ? (
                                                    <Loader2 className="h-4 w-4 animate-spin" />
                                                ) : (
                                                    <Trash2 className="h-4 w-4 text-destructive" />
                                                )}
                                            </Button>
                                        </div>
                                    </TableCell>
                                </TableRow>
                            ))}
                        </TableBody>
                    </Table>
                </div>
            )}

            <CreateCredentialDialog
                open={isAddDialogOpen}
                onOpenChange={setIsAddDialogOpen}
                onCreated={handleCredentialCreated}
            />
        </div>
    );
}
