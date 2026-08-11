import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "../../utils/cn"

const buttonVariants = cva(
  "inline-flex items-center justify-center whitespace-nowrap rounded-sm text-xs font-semibold transition-all duration-150 active:scale-[0.98] disabled:pointer-events-none disabled:opacity-50 select-none",
  {
    variants: {
      variant: {
        default: "bg-bg-card text-text-primary border border-border-color hover:border-border-color hover:bg-sidebar-item-hover shadow-xs",
        primary: "bg-accent-cyan text-on-accent font-bold hover:brightness-110 shadow-xs border border-cyan-300/30",
        destructive: "bg-danger text-white hover:bg-danger/90 shadow-xs border border-red-400/30",
        outline: "border border-border-color bg-transparent text-text-primary hover:bg-sidebar-item-hover hover:border-border-color",
        secondary: "bg-sidebar-item-hover text-text-primary border border-border-color hover:bg-sidebar-item-hover hover:border-border-color",
        ghost: "bg-transparent text-text-muted hover:bg-sidebar-item-hover hover:text-text-primary",
        link: "text-accent-cyan underline-offset-4 hover:underline",
      },
      size: {
        default: "h-8 px-3 py-1 text-xs rounded-sm",
        sm: "h-6 rounded-sm px-2 text-[11px]",
        lg: "h-9 rounded-sm px-4 text-xs",
        icon: "h-7 w-7 rounded-sm",
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
