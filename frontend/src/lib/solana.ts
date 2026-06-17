import { solToLamports } from "@bitagents/shared";
import { PublicKey, SystemProgram, Transaction, type Connection } from "@solana/web3.js";

export function toPublicKey(address: string): PublicKey {
  if (!address || address.includes("REPLACE")) {
    throw new Error("Treasury wallet is not configured. Set TREASURY_WALLET in your environment.");
  }
  return new PublicKey(address);
}

// Devnet-only SOL transfer used for task fee payments. The wallet adapter
// connection is always pointed at devnet (see SolanaProviders), so this never
// moves mainnet funds.
export async function sendSolTransfer({
  connection,
  from,
  to,
  amountSol,
  sendTransaction
}: {
  connection: Connection;
  from: PublicKey;
  to: PublicKey;
  amountSol: number;
  sendTransaction: (transaction: Transaction, connection: Connection) => Promise<string>;
}): Promise<string> {
  const transaction = new Transaction().add(
    SystemProgram.transfer({
      fromPubkey: from,
      toPubkey: to,
      lamports: solToLamports(amountSol)
    })
  );

  const signature = await sendTransaction(transaction, connection);
  const latest = await connection.getLatestBlockhash("confirmed");
  await connection.confirmTransaction({ signature, ...latest }, "confirmed");
  return signature;
}
