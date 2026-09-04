import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "../../utils/cn"

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-sm border px-2 py-0.5 text-[10px] font-semibold tracking-wide uppercase transition-all duration-150 backdrop-blur-sm",
  {
    variants: {
      variant: {
        default: "border-border-color bg-sidebar-item-hover text-text-primary",
        secondary: "border-border-color bg-sidebar-item-hover text-text-muted",
        destructive: "border-danger/30 bg-danger/15 text-danger shadow-[0_0_8px_-1px_rgba(239,68,68,0.3)]",
        outline: "border-border-color/60 text-text-secondary bg-transparent",
        success: "border-success/30 bg-success/15 text-success shadow-[0_0_8px_-1px_rgba(16,185,129,0.3)]",
        warning: "border-warning/30 bg-warning/15 text-warning shadow-[0_0_8px_-1px_rgba(245,158,11,0.3)]",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  )
}

export { Badge, badgeVariants }
