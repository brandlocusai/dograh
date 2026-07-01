"use client";

import {
  ArrowUpRight,
  CheckCircle2,
  CircleDollarSign,
  Coins,
  CreditCard,
  History,
  Loader2,
  Plus,
  XCircle,
  Calculator,
} from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useAuth } from "@/lib/auth";

interface Transaction {
  id: number;
  amount_usd: number;
  status: string;
  stripe_session_id: string | null;
  created_at: string;
}

function BillingContent() {
  const { user, getAccessToken, redirectToLogin, loading } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();

  const [balance, setBalance] = useState<number>(0.0);
  const [pricePerSecond, setPricePerSecond] = useState<number | null>(null);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  
  const [isLoadingBalance, setIsLoadingBalance] = useState(true);
  const [isLoadingTransactions, setIsLoadingTransactions] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  
  const [customAmount, setCustomAmount] = useState<string>("");
  const [selectedAmount, setSelectedAmount] = useState<number | null>(25);

  const [platformInfraRate, setPlatformInfraRate] = useState<number>(0.055);
  const [monthlyMinutes, setMonthlyMinutes] = useState<number>(100);
  const [selectedLLM, setSelectedLLM] = useState<string>("openai/gpt-4.1-mini");
  const [selectedTTS, setSelectedTTS] = useState<string>("elevenlabs");
  const [selectedSTT, setSelectedSTT] = useState<string>("deepgram");
  const [apiRates, setApiRates] = useState<any>(null);

  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "";

  // Fetch billing data
  const fetchBillingData = useCallback(async () => {
    if (loading || !user) return;

    try {
      setIsLoadingBalance(true);
      setIsLoadingTransactions(true);
      
      const token = await getAccessToken();
      const headers = {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      };

      // Fetch balance
      const balanceRes = await fetch(`${backendUrl}/api/v1/billing/balance`, { headers });
      if (balanceRes.ok) {
        const balanceData = await balanceRes.json();
        setBalance(balanceData.balance_usd);
        setPricePerSecond(balanceData.price_per_second_usd);
        if (balanceData.platform_infra_rate_per_minute !== undefined) {
          setPlatformInfraRate(balanceData.platform_infra_rate_per_minute);
        }
        if (balanceData.estimated_rates) {
          setApiRates(balanceData.estimated_rates);
        }
      }

      // Fetch transactions
      const txRes = await fetch(`${backendUrl}/api/v1/billing/transactions?limit=10`, { headers });
      if (txRes.ok) {
        const txData = await txRes.json();
        setTransactions(txData.transactions);
        setTotalCount(txData.total_count);
      }
    } catch (err) {
      console.error("Error fetching billing data:", err);
      toast.error("Failed to load billing information.");
    } finally {
      setIsLoadingBalance(false);
      setIsLoadingTransactions(false);
    }
  }, [loading, user, backendUrl, getAccessToken]);

  // Handle Stripe redirect callbacks
  useEffect(() => {
    const success = searchParams.get("success");
    const cancel = searchParams.get("cancel");
    const sessionId = searchParams.get("session_id");

    if (success === "true" && sessionId) {
      const verifySession = async () => {
        try {
          setIsLoadingBalance(true);
          const token = await getAccessToken();
          const response = await fetch(`${backendUrl}/api/v1/billing/verify-session`, {
            method: "POST",
            headers: {
              Authorization: `Bearer ${token}`,
              "Content-Type": "application/json",
            },
            body: JSON.stringify({ session_id: sessionId }),
          });

          if (!response.ok) {
            throw new Error("Failed to verify session");
          }

          const data = await response.json();
          setBalance(data.balance_usd);
          setPricePerSecond(data.price_per_second_usd);
          if (data.platform_infra_rate_per_minute !== undefined) {
            setPlatformInfraRate(data.platform_infra_rate_per_minute);
          }
          if (data.estimated_rates) {
            setApiRates(data.estimated_rates);
          }
          
          toast.success("Payment successful! Your balance has been updated.", {
            description: `Session ID: ${sessionId.slice(0, 15)}...`,
            duration: 5000,
          });

          // Refresh transactions list
          const headers = {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          };
          const txRes = await fetch(`${backendUrl}/api/v1/billing/transactions?limit=10`, { headers });
          if (txRes.ok) {
            const txData = await txRes.json();
            setTransactions(txData.transactions);
            setTotalCount(txData.total_count);
          }
        } catch (err) {
          console.error("Error verifying Stripe session:", err);
          toast.error("Could not verify payment immediately, but it will be processed shortly.", {
            description: "Please refresh the page in a few moments.",
            duration: 6000,
          });
          fetchBillingData();
        } finally {
          setIsLoadingBalance(false);
          router.replace("/billing");
        }
      };

      verifySession();
    } else if (success === "true") {
      toast.success("Payment successful! Your balance has been updated.", {
        duration: 5000,
      });
      fetchBillingData();
      router.replace("/billing");
    } else if (cancel === "true") {
      toast.error("Payment cancelled.", {
        description: "No funds were added to your account.",
        duration: 4000,
      });
      router.replace("/billing");
    }
  }, [searchParams, router, backendUrl, getAccessToken, fetchBillingData]);

  useEffect(() => {
    if (!loading && !user) {
      redirectToLogin();
    } else {
      fetchBillingData();
    }
  }, [loading, user, redirectToLogin, fetchBillingData]);

  // Handle Top-Up
  const handleTopUp = async () => {
    const amountToPay = selectedAmount || parseFloat(customAmount);
    if (!amountToPay || isNaN(amountToPay) || amountToPay < 1.0) {
      toast.error("Please select or enter a valid amount (minimum $1.00).");
      return;
    }

    try {
      setIsSubmitting(true);
      const token = await getAccessToken();
      
      const response = await fetch(`${backendUrl}/api/v1/billing/checkout-session`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ amount_usd: amountToPay }),
      });

      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.detail || "Failed to create checkout session");
      }

      const data = await response.json();
      if (data.url) {
        // Redirect to Stripe Checkout
        window.location.href = data.url;
      } else {
        throw new Error("Stripe Checkout URL not returned");
      }
    } catch (err: any) {
      console.error("Stripe Checkout Error:", err);
      toast.error(err.message || "An error occurred while connecting to Stripe.");
      setIsSubmitting(false);
    }
  };

  const quickAmounts = [10, 25, 50, 100];

  const formatPricePerMinute = (pps: number | null) => {
    const rate = pps !== null ? pps : 0.0025; // Default: $0.0025 per second ($0.15/min)
    return `$${(rate * 60).toFixed(2)}`;
  };

  if (loading || isLoadingBalance && transactions.length === 0) {
    return (
      <div className="flex h-[80vh] items-center justify-center">
        <div className="flex flex-col items-center gap-2">
          <Loader2 className="h-10 w-10 animate-spin text-primary" />
          <p className="text-sm text-muted-foreground">Loading billing details...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto space-y-8 px-4 py-8 max-w-6xl animate-in fade-in duration-500">
      {/* Header */}
      <div className="flex flex-col gap-2">
        <h1 className="text-4xl font-extrabold tracking-tight bg-gradient-to-r from-foreground to-foreground/70 bg-clip-text">
          Billing & Balance
        </h1>
        <p className="text-muted-foreground text-lg">
          Manage your prepaid credits, view transaction history, and top up your balance via Stripe.
        </p>
      </div>

      {/* Main Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        
        {/* Left column: Balance & Top-up */}
        <div className="lg:col-span-2 space-y-8">
          
          {/* Balance Card */}
          <Card className="relative overflow-hidden border border-border/40 bg-gradient-to-br from-card/80 to-card/30 backdrop-blur-md shadow-xl">
            <div className="absolute top-0 right-0 -mt-4 -mr-4 w-32 h-32 bg-primary/10 rounded-full blur-2xl pointer-events-none" />
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardDescription className="text-sm font-medium uppercase tracking-wider">
                  Available Credits
                </CardDescription>
                <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-500 border border-emerald-500/20 text-xs font-semibold">
                  <span className="relative flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                  </span>
                  Active
                </div>
              </div>
              <CardTitle className="text-5xl font-black tracking-tight mt-1">
                ${balance.toFixed(2)}
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-4 border-t border-border/20">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 text-sm text-muted-foreground">
                <div className="flex items-center gap-2">
                  <Coins className="h-4 w-4 text-primary" />
                  <span>
                    Current Rate: <strong className="text-foreground">{formatPricePerMinute(pricePerSecond)} / min</strong> ({pricePerSecond !== null ? `$${pricePerSecond.toFixed(4)}` : "$0.0025"}/sec)
                  </span>
                </div>
                <div>
                  Min balance to call: <strong className="text-foreground">$0.10</strong>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Top Up Section */}
          <Card className="border border-border/40 bg-card/50 backdrop-blur-md shadow-lg">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-xl font-bold">
                <CreditCard className="h-5 w-5 text-primary" />
                Add Funds
              </CardTitle>
              <CardDescription>
                Choose an amount to top up your organization's balance securely via Stripe.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              
              {/* Quick Select Grid */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {quickAmounts.map((amount) => (
                  <Button
                    key={amount}
                    type="button"
                    variant={selectedAmount === amount ? "default" : "outline"}
                    className={`h-14 text-base font-semibold transition-all duration-200 ${
                      selectedAmount === amount 
                        ? "shadow-lg shadow-primary/20 scale-[1.02]" 
                        : "hover:bg-accent/50"
                    }`}
                    onClick={() => {
                      setSelectedAmount(amount);
                      setCustomAmount("");
                    }}
                  >
                    <Plus className="mr-1 h-4 w-4 opacity-70" />
                    ${amount}
                  </Button>
                ))}
              </div>

              {/* Custom Amount Input */}
              <div className="space-y-2">
                <Label htmlFor="custom-amount" className="text-sm font-semibold">
                  Or enter a custom amount (USD)
                </Label>
                <div className="relative">
                  <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground text-lg font-medium">
                    $
                  </span>
                  <Input
                    id="custom-amount"
                    type="number"
                    min="1.00"
                    step="0.01"
                    placeholder="Enter amount (Min $1.00)"
                    value={customAmount}
                    onChange={(e) => {
                      setCustomAmount(e.target.value);
                      setSelectedAmount(null);
                    }}
                    className="pl-8 h-12 text-lg font-medium focus-visible:ring-primary/30"
                  />
                </div>
              </div>

              {/* Action Button */}
              <Button
                onClick={handleTopUp}
                disabled={isSubmitting || (!selectedAmount && (!customAmount || parseFloat(customAmount) < 1.0))}
                className="w-full h-12 text-base font-bold shadow-lg shadow-primary/10 transition-all hover:shadow-primary/20"
              >
                {isSubmitting ? (
                  <>
                    <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                    Connecting to Stripe...
                  </>
                ) : (
                  <>
                    Pay with Stripe
                    <ArrowUpRight className="ml-2 h-5 w-5" />
                  </>
                )}
              </Button>
            </CardContent>
          </Card>
        </div>

        {/* Right column: Info / How it works */}
        <div className="space-y-6">
          <Card className="border border-border/40 bg-card/30 backdrop-blur-md">
            <CardHeader>
              <CardTitle className="text-lg font-bold">How Billing Works</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 text-sm text-muted-foreground">
              <div className="space-y-1">
                <h4 className="font-semibold text-foreground">Prepaid Credit System</h4>
                <p>You add funds to your account, and your calls are billed per-second in real time based on call duration.</p>
              </div>
              <div className="space-y-1">
                <h4 className="font-semibold text-foreground">Threshold & Interruptions</h4>
                <p>A minimum balance of <strong>$0.10</strong> is required to initiate a call. If your balance hits $0.00, active calls will be terminated and new ones prevented.</p>
              </div>
              <div className="space-y-1">
                <h4 className="font-semibold text-foreground">Secure Payments</h4>
                <p>All payments are processed securely through Stripe. We do not store your credit card information.</p>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Cost Estimator Section */}
      {(() => {
        const llmOptions = [
          { id: "openai/gpt-4.1-mini", name: "GPT 4.1 Mini", rate: apiRates?.llm?.["openai/gpt-4.1-mini"] ?? 0.016 },
          { id: "openai/gpt-4.1", name: "GPT 4.1", rate: apiRates?.llm?.["openai/gpt-4.1"] ?? 0.070 },
          { id: "anthropic/claude-sonnet-4", name: "Claude 3.5 Sonnet", rate: apiRates?.llm?.["anthropic/claude-sonnet-4"] ?? 0.060 },
          { id: "google/gemini-2.5-flash", name: "Gemini 2.5 Flash", rate: apiRates?.llm?.["google/gemini-2.5-flash"] ?? 0.012 },
          { id: "meta-llama/llama-3.3-70b-instruct", name: "Llama 3.3 70B", rate: apiRates?.llm?.["meta-llama/llama-3.3-70b-instruct"] ?? 0.012 },
          { id: "deepseek/deepseek-chat-v3-0324", name: "DeepSeek V3", rate: apiRates?.llm?.["deepseek/deepseek-chat-v3-0324"] ?? 0.010 }
        ];

        const ttsOptions = [
          { id: "elevenlabs", name: "ElevenLabs", rate: apiRates?.tts?.["elevenlabs"] ?? 0.040 },
          { id: "deepgram", name: "Deepgram Aura", rate: apiRates?.tts?.["deepgram"] ?? 0.024 },
          { id: "openai", name: "OpenAI TTS", rate: apiRates?.tts?.["openai"] ?? 0.030 }
        ];

        const selectedLLMObj = llmOptions.find(o => o.id === selectedLLM) || llmOptions[0];
        const selectedTTSObj = ttsOptions.find(o => o.id === selectedTTS) || ttsOptions[0];
        const platformRatePerMin = platformInfraRate;

        const totalCostPerMin = selectedLLMObj.rate + selectedTTSObj.rate + platformRatePerMin;
        const totalMonthlyCost = totalCostPerMin * monthlyMinutes;

        return (
          <Card className="border border-border/40 bg-gradient-to-br from-card/60 to-card/25 backdrop-blur-md shadow-xl overflow-hidden">
            <CardHeader className="border-b border-border/10 pb-4">
              <CardTitle className="flex items-center gap-2 text-xl font-bold">
                <Calculator className="h-5 w-5 text-primary" />
                Interactive Call Cost Estimator
              </CardTitle>
              <CardDescription>
                Select your LLM and Voice configuration, and adjust your estimated monthly call volume in minutes.
              </CardDescription>
            </CardHeader>
            <CardContent className="pt-6">
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                {/* Left Columns - Inputs */}
                <div className="lg:col-span-2 space-y-6">
                  {/* Slider */}
                  <div className="space-y-3 bg-muted/20 p-4 rounded-xl border border-border/20">
                    <div className="flex items-center justify-between">
                      <Label className="text-sm font-semibold text-foreground">Monthly Call Duration (Minutes)</Label>
                      <span className="text-2xl font-black text-primary font-mono">{monthlyMinutes} min</span>
                    </div>
                    <input
                      type="range"
                      min="10"
                      max="5000"
                      step="10"
                      value={monthlyMinutes}
                      onChange={(e) => setMonthlyMinutes(parseInt(e.target.value))}
                      className="w-full h-2 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-primary"
                    />
                    <div className="flex justify-between text-xs text-muted-foreground font-mono">
                      <span>10m</span>
                      <span>1,000m</span>
                      <span>2,500m</span>
                      <span>5,000m</span>
                    </div>
                  </div>

                  {/* Options Selection */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    {/* LLM Selection */}
                    <div className="space-y-3 bg-muted/10 p-4 rounded-xl border border-border/20">
                      <Label className="text-sm font-bold uppercase tracking-wider text-muted-foreground block">
                        Choose Language Model (LLM)
                      </Label>
                      <div className="grid grid-cols-2 gap-2">
                        {llmOptions.map((opt) => (
                          <Button
                            key={opt.id}
                            type="button"
                            variant={selectedLLM === opt.id ? "default" : "outline"}
                            size="sm"
                            onClick={() => setSelectedLLM(opt.id)}
                            className={`h-11 text-xs font-semibold ${
                              selectedLLM === opt.id 
                                ? "shadow-md shadow-primary/20 scale-[1.01]" 
                                : "hover:bg-accent/40"
                            }`}
                          >
                            {opt.name}
                          </Button>
                        ))}
                      </div>
                    </div>

                    {/* TTS Selection */}
                    <div className="space-y-3 bg-muted/10 p-4 rounded-xl border border-border/20">
                      <Label className="text-sm font-bold uppercase tracking-wider text-muted-foreground block">
                        Choose Voice Engine (TTS)
                      </Label>
                      <div className="flex flex-col gap-2">
                        {ttsOptions.map((opt) => (
                          <Button
                            key={opt.id}
                            type="button"
                            variant={selectedTTS === opt.id ? "default" : "outline"}
                            onClick={() => setSelectedTTS(opt.id)}
                            className={`h-11 text-xs font-semibold justify-between px-4 ${
                              selectedTTS === opt.id 
                                ? "shadow-md shadow-primary/20 scale-[1.01]" 
                                : "hover:bg-accent/40"
                            }`}
                          >
                            <span>{opt.name}</span>
                            <span className="font-mono text-muted-foreground">${opt.rate.toFixed(3)}/min</span>
                          </Button>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Right Column - Results */}
                <div className="bg-muted/30 border border-border/30 rounded-2xl p-6 flex flex-col justify-between relative">
                  <div className="space-y-6">
                    <div>
                      <h3 className="text-xs uppercase tracking-wider font-semibold text-muted-foreground">Estimated Cost per Minute</h3>
                      <div className="text-4xl font-extrabold tracking-tight mt-1 text-foreground">
                        ${totalCostPerMin.toFixed(3)}<span className="text-lg font-medium text-muted-foreground">/min</span>
                      </div>
                    </div>

                    <div className="space-y-3.5 border-t border-border/20 pt-4 text-sm">
                      <div className="flex justify-between items-center text-muted-foreground">
                        <span>LLM Cost</span>
                        <span className="font-mono text-foreground font-semibold">${selectedLLMObj.rate.toFixed(3)}/min</span>
                      </div>
                      <div className="flex justify-between items-center text-muted-foreground">
                        <span>VCall Voice Infra</span>
                        <span className="font-mono text-foreground font-semibold">${platformRatePerMin.toFixed(3)}/min</span>
                      </div>
                      <div className="flex justify-between items-center text-muted-foreground">
                        <span>TTS Cost</span>
                        <span className="font-mono text-foreground font-semibold">${selectedTTSObj.rate.toFixed(3)}/min</span>
                      </div>
                      <div className="flex justify-between items-center text-muted-foreground">
                        <span>Telephony Cost</span>
                        <span className="font-mono text-foreground font-semibold">$0.000/min</span>
                      </div>
                    </div>
                  </div>

                  <div className="border-t border-border/30 pt-6 mt-6">
                    <h4 className="text-xs uppercase tracking-wider font-semibold text-muted-foreground">Total per month</h4>
                    <div className="text-4xl font-black text-primary tracking-tight mt-1">
                      ${totalMonthlyCost.toFixed(2)}
                    </div>
                    <p className="text-[10px] text-muted-foreground mt-1">For pay-as-you-go call volume plan.</p>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        );
      })()}

      {/* Transaction History Section */}
      <Card className="border border-border/40 bg-card/40 backdrop-blur-md shadow-lg">
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2 text-xl font-bold">
              <History className="h-5 w-5 text-primary" />
              Transaction History
            </CardTitle>
            <CardDescription>
              Recent payments and top-ups made to your organization.
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent>
          {isLoadingTransactions ? (
            <div className="space-y-3 py-4">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-12 w-full animate-pulse bg-muted rounded" />
              ))}
            </div>
          ) : transactions.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              No transactions found. Your payment history will appear here.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead className="w-[150px]">Transaction ID</TableHead>
                    <TableHead>Date</TableHead>
                    <TableHead>Stripe Session ID</TableHead>
                    <TableHead>Amount</TableHead>
                    <TableHead className="text-right">Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {transactions.map((tx) => (
                    <TableRow key={tx.id} className="hover:bg-muted/30">
                      <TableCell className="font-mono font-medium">#{tx.id}</TableCell>
                      <TableCell>{new Date(tx.created_at).toLocaleString()}</TableCell>
                      <TableCell className="font-mono text-xs text-muted-foreground">
                        {tx.stripe_session_id ? `${tx.stripe_session_id.slice(0, 20)}...` : "N/A"}
                      </TableCell>
                      <TableCell className="font-semibold text-foreground">
                        ${tx.amount_usd.toFixed(2)}
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end">
                          {tx.status === "completed" ? (
                            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-500 border border-emerald-500/20">
                              <CheckCircle2 className="h-3 w-3" />
                              Completed
                            </span>
                          ) : tx.status === "pending" ? (
                            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-500 border border-amber-500/20">
                              <Loader2 className="h-3 w-3 animate-spin" />
                              Pending
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-500/10 text-rose-500 border border-rose-500/20">
                              <XCircle className="h-3 w-3" />
                              Failed
                            </span>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default function BillingPage() {
  return (
    <Suspense
      fallback={
        <div className="flex h-[80vh] items-center justify-center">
          <Loader2 className="h-10 w-10 animate-spin text-primary" />
        </div>
      }
    >
      <BillingContent />
    </Suspense>
  );
}