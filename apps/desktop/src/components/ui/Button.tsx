import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "../../utils/cn"

const buttonVariants = cva(
  "inline-flex items-center justify-center whitespace-nowrap rounded-lg text-sm font-semibold transition-all duration-200 cubic-bezier(0.16, 1, 0.3, 1) active:scale-[0.98] disabled:pointer-events-none disabled:opacity-50 select-none",
  {
    variants: {
      variant: {
        // Neutral solid — theme-aware surface with soft elevation
        default: "bg-bg-card text-text-primary border border-border-color hover:border-border-color hover:bg-sidebar-item-hover shadow-sm",
        // The primary brand action — subtle glowing accent
        primary: "bg-accent-cyan text-on-accent font-bold hover:brightness-110 shadow-[0_0_15px_-3px_rgba(0,229,255,0.4)] border border-cyan-300/30",
        destructive: "bg-danger text-white hover:bg-danger/90 shadow-[0_0_12px_-2px_rgba(239,68,68,0.4)] border border-red-400/30",
        outline: "border border-border-color bg-transparent text-text-primary hover:bg-sidebar-item-hover hover:border-border-color",
        secondary: "bg-sidebar-item-hover text-text-primary border border-border-color hover:bg-sidebar-item-hover hover:border-border-color",
        ghost: "bg-transparent text-text-muted hover:bg-sidebar-item-hover hover:text-text-primary",
        link: "text-accent-cyan underline-offset-4 hover:underline",
      },
      size: {
        default: "h-9 px-4 py-2 text-xs",
        sm: "h-8 rounded-md px-3 text-xs",
        lg: "h-10 rounded-lg px-6 text-sm",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    return (
      <button
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    )
  }
)
Button.displayName = "Button"

export { Button, buttonVariants }
