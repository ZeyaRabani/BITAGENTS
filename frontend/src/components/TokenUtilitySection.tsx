import { TOKEN_UTILITY } from "@/lib/content";

export function TokenUtilitySection() {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {TOKEN_UTILITY.map((item) => (
        <div key={item.title} className="pixel-corners border border-border bg-surface p-5">
          <h3 className="font-display text-base font-semibold text-foreground">{item.title}</h3>
          <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{item.body}</p>
        </div>
      ))}
    </div>
  );
}
