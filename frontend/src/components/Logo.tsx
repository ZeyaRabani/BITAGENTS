import Image from "next/image";
import logoAsset from "@/assets/bit-agents-logo-transparent.png";

export function Logo({ className = "h-16 w-auto" }: { className?: string }) {
  return (
    <Image
      src={logoAsset}
      alt="BITAGENTS"
      className={className}
      priority
    />
  );
}
