import { cn } from "@/lib/cn";

type Props = {
  eyebrow: string;
  headline: string;
  subheadline: string;
  accentColor?: string;
  className?: string;
};

export function ChapterHero({ eyebrow, headline, subheadline, accentColor = "#ED7238", className }: Props) {
  return (
    <div className={cn("py-8 px-8 border-b border-surface-3 bg-white", className)}>
      <p
        className="text-2xs font-mono uppercase tracking-[0.14em] mb-2 font-medium"
        style={{ color: accentColor }}
      >
        {eyebrow}
      </p>
      <h1
        className="display-gothic text-4xl text-txt-primary mb-3"
        style={{ fontSynthesis: "none" }}
      >
        {headline}
      </h1>
      <p className="text-sm text-txt-secondary max-w-2xl leading-relaxed">{subheadline}</p>
    </div>
  );
}
