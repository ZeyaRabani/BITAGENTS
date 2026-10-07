import type { PublicKey } from "@solana/web3.js";

export type SignedProviderListing = {
    provider: string;
    wallet: string;
    gpu: string;
    hours: number;
    price: number;
    signature: string;
    message: string;
    timestamp: number;
};

export function buildProviderMessage(params: {
    wallet: PublicKey;
    gpu: string;
    hours: number;
    price: number;
}) {
    return `
BITAGENTS Provider Listing

wallet: ${params.wallet.toBase58()}
gpu: ${params.gpu}
hours: ${params.hours}
price: ${params.price}

timestamp: ${Date.now()}
`.trim();
}