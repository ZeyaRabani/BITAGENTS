import Image from "next/image";
import logoAsset from "@/assets/bitagents-wordmark-horizontal.png";

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
