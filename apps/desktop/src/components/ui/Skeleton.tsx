import React from 'react';
import { twMerge } from 'tailwind-merge';

interface SkeletonProps extends React.HTMLAttributes<HTMLDivElement> {}

export const Skeleton: React.FC<SkeletonProps> = ({ className, ...props }) => {
  return (
    <div
      className={twMerge(
        'animate-pulse rounded-md bg-sidebar-item-hover border border-border-color shadow-inner',
        className
      )}
      {...props}
    />
  );
};
