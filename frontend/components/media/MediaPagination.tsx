/**
 * MediaPagination - 媒体列表分页组件
 * 
 * 核心职责：
 * - 显示分页控制（上一页、页码按钮、下一页）
 * - 支持快速跳转到指定页码
 * - 显示总条数和当前页面信息
 * 
 * Props 说明：
 * - currentPage：当前页码（从 1 开始）
 * - totalPages：总页数
 * - totalItems：总条目数
 * - onPageChange：页码变更回调
 * 
 * 分页逻辑：
 * - 最多显示 5 个页码按钮
 * - 当前页在前 3 页时：显示 1-5
 * - 当前页在后 3 页时：显示 (totalPages-4) 到 totalPages
 * - 其他情况：显示 (currentPage-2) 到 (currentPage+2)
 * - 无数据或仅 1 页时隐藏分页组件
 * 
 * 视觉效果：
 * - 青色边框和发光效果
 * - 当前页高亮显示
 * - 禁用状态的上一页/下一页按钮（在第一/最后一页时）
 * 
 * @component
 */

'use client';

import { useState } from 'react';
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
  const [jumpPage, setJumpPage] = useState('');
  const [inputError, setInputError] = useState(false);

  if (totalItems === 0 || totalPages <= 1) {
    return null;
  }

  const handleJumpPageChange = (value: string) => {
    const numericValue = value.replace(/\D/g, '').slice(0, 5);
    setJumpPage(numericValue);
    setInputError(false);
  };

  const handleJumpPageSubmit = () => {
    const pageNum = parseInt(jumpPage, 10);
    
    if (!jumpPage.trim()) {
      setInputError(true);
      setTimeout(() => setInputError(false), 300);
      return;
    }
    
    if (pageNum < 1) {
      setInputError(true);
      setTimeout(() => setInputError(false), 300);
      return;
    }
    
    const targetPage = Math.min(pageNum, totalPages);
    onPageChange(targetPage);
    setJumpPage('');
  };

  const handleJumpPageKeyPress = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      handleJumpPageSubmit();
    }
  };

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
        
        <div className="flex items-center gap-2 ml-6">
          <span className="text-cyber-cyan/70 text-sm whitespace-nowrap">
            {t('pagination_jump_to')}
          </span>
          <input
            type="text"
            value={jumpPage}
            onChange={(e) => handleJumpPageChange(e.target.value)}
            onKeyPress={handleJumpPageKeyPress}
            placeholder={String(currentPage)}
            className={cn(
              "w-20 px-3 py-3 text-sm font-semibold text-center",
              "bg-transparent border text-cyber-cyan",
              "focus:outline-none transition-all placeholder-cyber-cyan/30",
              inputError 
                ? "border-cyber-red shadow-[0_0_20px_rgba(239,68,68,0.6)] animate-shake"
                : "border-cyber-cyan/50 focus:border-cyber-cyan focus:shadow-[0_0_20px_rgba(6,182,212,0.6)] focus:bg-cyber-cyan/5"
            )}
            style={{ backdropFilter: 'blur(10px)' }}
          />
          <span className="text-cyber-cyan/70 text-sm">
            {t('pagination_page_unit')}
          </span>
          <button
            onClick={handleJumpPageSubmit}
            className="bg-transparent border border-cyber-cyan text-cyber-cyan px-4 py-3 font-semibold text-sm hover:bg-cyber-cyan hover:text-black transition-all hover:scale-110"
            style={{ 
              backdropFilter: 'blur(10px)',
              boxShadow: '0 0 20px rgba(6, 182, 212, 0.3)',
            }}
          >
            {t('pagination_jump_btn')}
          </button>
        </div>
      </div>
    </div>
  );
}
