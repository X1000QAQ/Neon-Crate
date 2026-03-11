'use client';

import { ChevronLeft, ChevronRight } from 'lucide-react';
import { useLanguage } from '@/hooks/useLanguage';
import { cn } from '@/lib/utils';

interface MediaPaginationProps {
  currentPage: number;
  totalPages: number;
  totalItems: number;
  onPageChange: (page: number) => void;
}

export default function MediaPagination({
  currentPage,
  totalPages,
  totalItems,
  onPageChange,
}: MediaPaginationProps) {
  const { t } = useLanguage();

  if (totalItems === 0 || totalPages <= 1) {
    return null;
  }

  // 生成页码数组（最多显示5个页码）
  const getPageNumbers = () => {
    const pages: number[] = [];
    const maxVisible = 5;
    
    if (totalPages <= maxVisible) {
      for (let i = 1; i <= totalPages; i++) {
        pages.push(i);
      }
    } else {
      if (currentPage <= 3) {
        for (let i = 1; i <= maxVisible; i++) {
          pages.push(i);
        }
      } else if (currentPage >= totalPages - 2) {
        for (let i = totalPages - maxVisible + 1; i <= totalPages; i++) {
          pages.push(i);
        }
      } else {
        for (let i = currentPage - 2; i <= currentPage + 2; i++) {
          pages.push(i);
        }
      }
    }
    
    return pages;
  };

  return (
    <div className="relative bg-transparent border border-cyber-cyan/50 p-6 hover:border-cyber-cyan transition-all" style={{
      backdropFilter: 'blur(20px)',
      boxShadow: '0 0 40px rgba(6, 182, 212, 0.3), inset 0 0 40px rgba(6, 182, 212, 0.05)'
    }}>
      <div className="flex items-center justify-center gap-3">
        <button
          onClick={() => onPageChange(Math.max(1, currentPage - 1))}
          disabled={currentPage === 1}
          className="bg-transparent border border-cyber-cyan text-cyber-cyan px-5 py-3 font-semibold hover:bg-cyber-cyan hover:text-black transition-all disabled:opacity-50 disabled:cursor-not-allowed hover:scale-110"
          style={{ 
            backdropFilter: 'blur(10px)',
            boxShadow: '0 0 20px rgba(6, 182, 212, 0.3)',
          }}
        >
          <ChevronLeft className="w-5 h-5" />
        </button>
        
        {getPageNumbers().map((page) => (
          <button
            key={page}
            onClick={() => onPageChange(page)}
            className={cn(
              "px-5 py-3 font-semibold text-sm border transition-all hover:scale-110",
              page === currentPage 
                ? "bg-cyber-cyan text-black border-cyber-cyan" 
                : "bg-transparent text-cyber-cyan border-cyber-cyan hover:bg-cyber-cyan hover:text-black"
            )}
            style={{ 
              backdropFilter: 'blur(10px)', 
              boxShadow: page === currentPage ? '0 0 30px rgba(6, 182, 212, 0.8)' : '0 0 15px rgba(6, 182, 212, 0.3)',
            }}
          >
            {page}
          </button>
        ))}
        
        <button
          onClick={() => onPageChange(Math.min(totalPages, currentPage + 1))}
          disabled={currentPage >= totalPages}
          className="bg-transparent border border-cyber-cyan text-cyber-cyan px-5 py-3 font-semibold hover:bg-cyber-cyan hover:text-black transition-all disabled:opacity-50 disabled:cursor-not-allowed hover:scale-110"
          style={{ 
            backdropFilter: 'blur(10px)',
            boxShadow: '0 0 20px rgba(6, 182, 212, 0.3)',
          }}
        >
          <ChevronRight className="w-5 h-5" />
        </button>
      </div>
    </div>
  );
}
