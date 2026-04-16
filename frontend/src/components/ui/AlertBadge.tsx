import { cn } from "@/lib/cn";
import { ALERT_LEVELS } from "@/lib/tokens";

type Props = {
  level: string;
  className?: string;
};

export function AlertBadge({ level, className }: Props) {
  const config = ALERT_LEVELS[level as keyof typeof ALERT_LEVELS] ?? ALERT_LEVELS.critical;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 px-2 py-0.5 rounded-pill text-2xs font-medium",
        className
      )}
      style={{
        backgroundColor: `${config.color}18`,
        color: config.color,
        border: `1px solid ${config.color}30`,
      }}
    >
      <span
        className="w-1.5 h-1.5 rounded-full"
        style={{ backgroundColor: config.color }}
      />
      {config.label}
    </span>
  );
}
