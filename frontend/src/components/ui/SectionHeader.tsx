import { cn } from "@/lib/cn";

type Props = {
  step: string;
  title: string;
  subtitle?: string;
  className?: string;
  accentColor?: string;
};

export function SectionHeader({ step, title, subtitle, className, accentColor = "#ED7238" }: Props) {
  return (
    <div className={cn("mb-6", className)}>
      <div className="flex items-center gap-2 mb-1">
        <span
          className="text-2xs font-mono uppercase tracking-[0.12em] font-medium"
          style={{ color: accentColor }}
        >
          {step}
        </span>
        <span className="h-px flex-1 bg-surface-3 max-w-[40px]" />
      </div>
      <h2 className="text-xl font-bold text-txt-primary leading-tight">{title}</h2>
      {subtitle && <p className="text-sm text-txt-muted mt-1 leading-relaxed">{subtitle}</p>}
    </div>
  );
}
