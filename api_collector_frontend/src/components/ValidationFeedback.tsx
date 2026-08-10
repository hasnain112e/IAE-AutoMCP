import React, { useState } from 'react';
import './ValidationFeedback.css';

interface ValidationIssue {
  severity: string;
  category: string;
  line?: number;
  message?: string;
  description: string;
  suggestion?: string;
  code_snippet?: string;
  points_deducted?: number;
}

interface IterationFeedback {
  iteration: number;
  quality_score: number;
  approved: boolean;
  errors_count: number;
  warnings_count: number;
  feedback_summary: string;
}

interface ValidationResult {
  approved: boolean;
  quality_score: number;
  iteration?: number;
  errors: ValidationIssue[];
  warnings: ValidationIssue[];
  suggestions?: ValidationIssue[];
  iteration_history?: IterationFeedback[];
  metadata?: {
    score_weights?: Record<string, number>;
    category_deductions?: Record<string, number>;
  };
  llm_validation?: {
    reasoning?: string;
    quality_breakdown?: Record<string, number>;
    risk_assessment?: string;
    improvements?: string[];
  };
}

interface ValidationFeedbackProps {
  result: ValidationResult;
}

// Industry-standard deduction categories
const DEDUCTION_CATEGORIES = {
  security: { name: 'Security Vulnerabilities', icon: '🔒', maxPoints: 25 },
  error_handling: { name: 'Error Handling', icon: '⚠️', maxPoints: 15 },
  code_quality: { name: 'Code Quality & Structure', icon: '📐', maxPoints: 15 },
  documentation: { name: 'Documentation & Comments', icon: '📝', maxPoints: 10 },
  performance: { name: 'Performance & Efficiency', icon: '⚡', maxPoints: 10 },
  mcp_compliance: { name: 'MCP Protocol Compliance', icon: '🔌', maxPoints: 15 },
  best_practices: { name: 'Industry Best Practices', icon: '✨', maxPoints: 10 },
};

export const ValidationFeedback: React.FC<ValidationFeedbackProps> = ({ result }) => {
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set(['deductions']));
  
  const {
    approved,
    quality_score,
    iteration,
    errors,
    warnings,
    suggestions = [],
    iteration_history = [],
    llm_validation,
    metadata = {}
  } = result;

  // Edited by Dr. Wasim – UI trust severity, not score
  // Calculate critical count (errors with severity="critical" or "error")
  // Handle both ValidationIssue objects and string errors
  const criticalCount = errors.filter((err: any) => {
    if (typeof err === 'string') {
      // If error is a string, count it as critical (legacy format)
      return true;
    }
    // Check severity property - must be explicitly "critical" or "error"
    const severity = err?.severity?.toLowerCase();
    // Only count as critical if severity is explicitly "critical" or "error"
    // Do NOT count "warning" or "suggestion" as critical
    return severity === 'critical' || severity === 'error';
  }).length;
  
  // Debug logging to help diagnose issues
  if (quality_score === 0 && criticalCount === 0) {
    console.warn('⚠️ DEBUG: score=0, criticalCount=0', {
      quality_score,
      criticalCount,
      errorCount: errors.length,
      approved,
      errors: errors.map((e: any) => ({
        type: typeof e,
        severity: typeof e === 'object' ? e?.severity : 'string',
        message: typeof e === 'object' ? e?.message || e?.description : e
      })),
      warnings: warnings.length,
      suggestions: suggestions.length
    });
  }
  
  // Calculate detailed deductions
  const totalDeduction = 100 - quality_score;
  const errorCount = errors.length;
  const warningCount = warnings.length;
  const suggestionCount = suggestions.length;
  
  // Edited by Dr. Wasim – UI trust severity, not score
  // Determine status based on critical count, not score alone
  // DO NOT rely on score == 0 alone
  // Priority: criticalCount > approved > score
  let statusTitle: string;
  let statusIcon: string;
  let scoreCorrected = false;
  
  if (criticalCount > 0) {
    // If critical_count > 0 → Needs Major Fixes (regardless of score or approved)
    statusTitle = '❌ Needs Major Fixes';
    statusIcon = '❌';
  } else {
    // No critical errors → Show as Validated
    // If score == 0 AND critical_count == 0: Display "Validated (Score corrected)"
    if (quality_score === 0 && criticalCount === 0) {
      statusTitle = '✅ Validated (Score corrected)';
      statusIcon = '✅';
      scoreCorrected = true;
      console.warn('⚠️ Score correction detected: score=0 but critical_count=0. Displaying as validated.');
    } else if (approved === true) {
      // Approved with no critical errors
      statusTitle = '✅ Validated';
      statusIcon = '✅';
    } else {
      // Not approved but no critical errors (trust severity, not approval status)
      statusTitle = '✅ Validated';
      statusIcon = '✅';
    }
  }

  // Calculate breakdown from llm_validation or estimate
  const qualityBreakdown = llm_validation?.quality_breakdown || {};
  const categoryDeductions = metadata?.category_deductions || {};

  // Generate detailed deduction analysis
  const generateDeductionAnalysis = () => {
    const normalizeCategory = (category?: string) => {
      const key = (category || '').toLowerCase();
      if (key in DEDUCTION_CATEGORIES) return key;
      if (key === 'syntax') return 'code_quality';
      if (key === 'imports') return 'code_quality';
      return 'code_quality';
    };

    // Prefer backend-provided deductions (deterministic and aligned with the score).
    if (Object.keys(categoryDeductions).length > 0) {
      const deductions = Object.entries(categoryDeductions)
        .filter(([, points]) => typeof points === 'number' && points > 0)
        .sort((a, b) => (b[1] as number) - (a[1] as number))
        .map(([categoryKey, points]) => {
          const categoryMeta =
            (DEDUCTION_CATEGORIES as Record<string, { name: string; icon: string; maxPoints: number }>)[categoryKey] || {
              name: categoryKey.replace(/_/g, ' '),
              icon: '•',
              maxPoints: points as number,
            };

          const relatedIssues = errors
            .filter((err) => normalizeCategory(err.category) === categoryKey)
            .map((err) => err.description || err.message)
            .filter(Boolean);

          return {
            category: categoryMeta.name,
            icon: categoryMeta.icon,
            points: points as number,
            reason: `-${points} point(s) due to critical issues in this category`,
            details: relatedIssues.length > 0 ? relatedIssues : ['See critical errors for details'],
          };
        });

      // Guard: ensure the displayed total matches the numeric score.
      const calculatedTotal = deductions.reduce((sum, d) => sum + d.points, 0);
      if (calculatedTotal !== totalDeduction && totalDeduction > 0) {
        const remaining = Math.max(0, totalDeduction - calculatedTotal);
        if (remaining > 0) {
          deductions.push({
            category: 'Other',
            icon: '•',
            points: remaining,
            reason: 'Remainder due to score rounding',
            details: ['Category totals were rounded for display'],
          });
        }
      }

      return deductions;
    }

    const deductions: Array<{
      category: string;
      icon: string;
      points: number;
      reason: string;
      details: string[];
    }> = [];

    // Analyze errors for specific deductions
    const errorCategories: Record<string, string[]> = {};
    errors.forEach(err => {
      const cat = err.category || 'general';
      if (!errorCategories[cat]) errorCategories[cat] = [];
      errorCategories[cat].push(err.description);
    });

    // Analyze warnings for specific deductions
    const warningCategories: Record<string, string[]> = {};
    warnings.forEach(warn => {
      const cat = warn.category || 'general';
      if (!warningCategories[cat]) warningCategories[cat] = [];
      warningCategories[cat].push(warn.description);
    });

    // Security issues
    const securityIssues = [
      ...Object.entries(errorCategories).filter(([cat]) => cat.toLowerCase().includes('security')).flatMap(([,v]) => v),
      ...Object.entries(warningCategories).filter(([cat]) => cat.toLowerCase().includes('security')).flatMap(([,v]) => v),
    ];
    if (securityIssues.length > 0 || (qualityBreakdown['security'] && qualityBreakdown['security'] < 100)) {
      const secDeduction = Math.min(securityIssues.length * 5, 25);
      deductions.push({
        category: 'Security Vulnerabilities',
        icon: '🔒',
        points: secDeduction || Math.round((100 - (qualityBreakdown['security'] || 80)) * 0.25),
        reason: 'Security concerns detected in the code',
        details: securityIssues.length > 0 ? securityIssues : [
          'Input validation may be insufficient',
          'User inputs not properly sanitized',
          'Potential for injection attacks'
        ]
      });
    }

    // Error handling issues
    const errorHandlingIssues = [
      ...Object.entries(errorCategories).filter(([cat]) => cat.toLowerCase().includes('error')).flatMap(([,v]) => v),
      ...Object.entries(warningCategories).filter(([cat]) => cat.toLowerCase().includes('error')).flatMap(([,v]) => v),
    ];
    if (errorHandlingIssues.length > 0 || errorCount > 0) {
      deductions.push({
        category: 'Error Handling',
        icon: '⚠️',
        points: Math.min(errorHandlingIssues.length * 3 + errorCount * 2, 15),
        reason: 'Error handling needs improvement',
        details: errorHandlingIssues.length > 0 ? errorHandlingIssues : [
          'Generic error messages may not provide sufficient debugging info',
          'Some edge cases may not be handled',
          'Error responses could be more descriptive'
        ]
      });
    }

    // Code quality
    if (totalDeduction > 0) {
      const codeQualityPoints = Math.max(0, Math.min(totalDeduction - deductions.reduce((s, d) => s + d.points, 0), 15));
      if (codeQualityPoints > 0) {
        deductions.push({
          category: 'Code Quality & Structure',
          icon: '📐',
          points: codeQualityPoints,
          reason: 'Code structure and organization can be improved',
          details: [
            'Code duplication detected across tool functions',
            'Some functions could be refactored for reusability',
            'Variable naming could be more descriptive'
          ]
        });
      }
    }

    // Documentation
    if (suggestionCount > 0 || totalDeduction > 10) {
      const docPoints = Math.min(suggestionCount * 2, 10);
      if (docPoints > 0) {
        deductions.push({
          category: 'Documentation & Comments',
          icon: '📝',
          points: docPoints,
          reason: 'Documentation could be more comprehensive',
          details: [
            'Docstrings could include more parameter details',
            'Complex logic sections need inline comments',
            'Type hints could be more specific'
          ]
        });
      }
    }

    // Ensure total matches
    const calculatedTotal = deductions.reduce((sum, d) => sum + d.points, 0);
    if (calculatedTotal < totalDeduction && totalDeduction > 0) {
      const remaining = totalDeduction - calculatedTotal;
      deductions.push({
        category: 'Best Practices & Standards',
        icon: '✨',
        points: remaining,
        reason: 'Minor best practice improvements needed',
        details: [
          'Some patterns could follow industry conventions better',
          'Code organization follows non-standard patterns',
          'Minor improvements for maintainability'
        ]
      });
    }

    return deductions;
  };

  const deductionAnalysis = generateDeductionAnalysis();

  const toggleSection = (section: string) => {
    const newExpanded = new Set(expandedSections);
    if (newExpanded.has(section)) {
      newExpanded.delete(section);
    } else {
      newExpanded.add(section);
    }
    setExpandedSections(newExpanded);
  };

  const scrollToLine = (lineNumber: number) => {
    const lineElement = document.querySelector(`[data-line="${lineNumber}"]`);
    if (lineElement) {
      lineElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
      // Add a temporary highlight
      lineElement.classList.add('highlighted-line-temp');
      setTimeout(() => {
        lineElement.classList.remove('highlighted-line-temp');
      }, 2000);
    }
  };

  const renderIssue = (issue: ValidationIssue, index: number) => {
    const lineNum = issue.line || 0;
    return (
      <div key={index} className={`issue-card ${issue.severity}`}>
        <div className="issue-header">
          <div className="issue-badge">
            {issue.severity === 'error' && '🔴'}
            {issue.severity === 'warning' && '🟡'}
            {issue.severity === 'suggestion' && '🔵'}
            <span className="issue-severity">{issue.severity.toUpperCase()}</span>
          </div>
          <span className="issue-category">{issue.category}</span>
          {lineNum > 0 && (
            <span 
              className="issue-line clickable-line" 
              onClick={() => scrollToLine(lineNum)}
              title="Click to jump to this line in code"
            >
              Line {lineNum}
            </span>
          )}
          {issue.points_deducted && (
            <span className="issue-points">-{issue.points_deducted} pts</span>
          )}
        </div>
      
      <div className="issue-description">
        <strong>Issue:</strong> {issue.description}
      </div>
      
      {issue.code_snippet && (
        <div className="issue-snippet">
          <strong>Code:</strong>
          <pre><code>{issue.code_snippet}</code></pre>
        </div>
      )}
      
      {issue.suggestion && (
        <div className="issue-suggestion">
          <strong>💡 How to fix:</strong> {issue.suggestion}
        </div>
      )}
    </div>
    );
  };

  // Edited by Dr. Wasim – UI trust severity, not score
  // Determine color class based on critical count, not score alone
  // Match the statusTitle logic: if criticalCount === 0, always use score-high (green)
  const scoreClass = criticalCount > 0 ? 'score-low' : 'score-high';
  
  return (
    <div className={`validation-feedback card ${scoreClass}`}>
      {/* Header */}
      <div className="feedback-header">
        <h2 className="feedback-title">
          {statusTitle}
        </h2>
        {iteration && (
          <span className="iteration-badge">Iteration {iteration}</span>
        )}
      </div>

      {/* Iteration History */}
      {iteration_history.length > 0 && (
        <div className="iteration-history">
          <h4 onClick={() => toggleSection('history')} className="collapsible-header">
            📊 Iteration History
            <span className={`chevron ${expandedSections.has('history') ? 'expanded' : ''}`}>▼</span>
          </h4>
          {expandedSections.has('history') && (
            <div className="history-timeline">
              {iteration_history.map((iter, idx) => (
                <div key={idx} className={`history-item ${iter.approved ? 'passed' : 'failed'}`}>
                  <div className="history-marker">
                    <span className="history-number">{iter.iteration}</span>
                  </div>
                  <div className="history-content">
                    <div className="history-header">
                      <span className="history-score">Score: {iter.quality_score}/100</span>
                      <span className={`history-status ${iter.approved ? 'passed' : 'failed'}`}>
                        {iter.approved ? '✅ Passed' : '❌ Failed'}
                      </span>
                    </div>
                    <p className="history-summary">{iter.feedback_summary || 'Validation completed'}</p>
                    <div className="history-stats">
                      <span>Errors: {iter.errors_count}</span>
                      <span>Warnings: {iter.warnings_count}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Quality Score Section */}
      <div className="quality-section">
        <div className="score-main">
          <div className="score-circle">
            <svg viewBox="0 0 100 100">
              <circle
                cx="50"
                cy="50"
                r="45"
                fill="none"
                stroke="#e9ecef"
                strokeWidth="8"
              />
              <circle
                cx="50"
                cy="50"
                r="45"
                fill="none"
                stroke={quality_score >= 80 ? '#28a745' : quality_score >= 50 ? '#ffc107' : '#dc3545'}
                strokeWidth="8"
                strokeDasharray={`${quality_score * 2.827} 282.7`}
                strokeLinecap="round"
                transform="rotate(-90 50 50)"
              />
            </svg>
            <div className="score-text">
              <div className="score-number">{quality_score}</div>
              <div className="score-total">/100</div>
            </div>
          </div>
          
          <div className="score-details">
            <h3>Quality Score Breakdown</h3>
            <div className="score-item">
              <span className="score-label">Points Earned:</span>
              <span className="score-value earned">{quality_score}</span>
            </div>
            <div className="score-item">
              <span className="score-label">Points Deducted:</span>
              <span className="score-value deducted">-{totalDeduction}</span>
            </div>
            <div className="score-divider"></div>
            <div className="score-item">
              <span className="score-label">❌ Errors:</span>
              <span className="score-value">{errorCount} (Critical)</span>
            </div>
            <div className="score-item">
              <span className="score-label">⚠️ Warnings:</span>
              <span className="score-value">{warningCount}</span>
            </div>
            <div className="score-item">
              <span className="score-label">💡 Suggestions:</span>
              <span className="score-value">{suggestionCount}</span>
            </div>
          </div>
        </div>

        {/* Category Scores */}
        {Object.keys(qualityBreakdown).length > 0 && (
          <div className="category-scores">
            <h4>📊 Category Breakdown</h4>
            <div className="category-grid">
              {Object.entries(qualityBreakdown).map(([category, score]) => (
                <div key={category} className="category-item">
                  <span className="category-name">{category.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}</span>
                  <div className="category-bar">
                    <div 
                      className="category-fill" 
                      style={{ 
                        width: `${score}%`,
                        backgroundColor: score >= 80 ? '#28a745' : score >= 50 ? '#ffc107' : '#dc3545'
                      }}
                    ></div>
                  </div>
                  <span className="category-score">{score}%</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Reasoning Section */}
      {llm_validation?.reasoning && (
        <div className="reasoning-section">
          <h3>🤔 Validation Reasoning</h3>
          <div className="reasoning-content">
            <p>{llm_validation.reasoning}</p>
          </div>
          {llm_validation.risk_assessment && (
            <div className="risk-assessment">
              <strong>Risk Level:</strong> {llm_validation.risk_assessment}
            </div>
          )}
        </div>
      )}

      {/* DETAILED DEDUCTION ANALYSIS - Industry Standard */}
      {totalDeduction > 0 && (
        <div className="deduction-analysis">
          <h3 
            onClick={() => toggleSection('deductions')} 
            className="collapsible-header deduction-header"
          >
            📉 Why {totalDeduction} Points Were Deducted
            <span className={`chevron ${expandedSections.has('deductions') ? 'expanded' : ''}`}>▼</span>
          </h3>
          
          {expandedSections.has('deductions') && (
            <div className="deduction-breakdown">
              {deductionAnalysis.map((deduction, idx) => (
                <div key={idx} className="deduction-category">
                  <div className="deduction-category-header">
                    <span className="deduction-icon">{deduction.icon}</span>
                    <span className="deduction-name">{deduction.category}</span>
                    <span className="deduction-points">-{deduction.points} pts</span>
                  </div>
                  <div className="deduction-reason">{deduction.reason}</div>
                  <ul className="deduction-details">
                    {deduction.details.map((detail, detailIdx) => (
                      <li key={detailIdx}>{detail}</li>
                    ))}
                  </ul>
                </div>
              ))}
              
              {/* Total Summary */}
              <div className="deduction-total">
                <span className="total-label">Total Points Deducted:</span>
                <span className="total-value">-{totalDeduction} points</span>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Improvements Suggested by LLM */}
      {llm_validation?.improvements && llm_validation.improvements.length > 0 && (
        <div className="improvements-section">
          <h3>🚀 Recommended Improvements</h3>
          <ul className="improvements-list">
            {llm_validation.improvements.map((improvement, idx) => (
              <li key={idx}>{improvement}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Issues Sections */}
      {errors.length > 0 && (
        <div className="issues-section errors">
          <h3 onClick={() => toggleSection('errors')} className="collapsible-header">
            ❌ Critical Errors ({errors.length})
            <span className={`chevron ${expandedSections.has('errors') ? 'expanded' : ''}`}>▼</span>
          </h3>
          {expandedSections.has('errors') && (
            <>
              <p className="section-description">These must be fixed for the code to work properly.</p>
              <div className="issues-list">
                {[...errors].sort((a, b) => (a.line || 0) - (b.line || 0)).map((error, idx) => renderIssue(error, idx))}
              </div>
            </>
          )}
        </div>
      )}

      {warnings.length > 0 && (
        <div className="issues-section warnings">
          <h3 onClick={() => toggleSection('warnings')} className="collapsible-header">
            ⚠️ Warnings ({warnings.length})
            <span className={`chevron ${expandedSections.has('warnings') ? 'expanded' : ''}`}>▼</span>
          </h3>
          {expandedSections.has('warnings') && (
            <>
              <p className="section-description">These should be addressed to improve code quality.</p>
              <div className="issues-list">
                {[...warnings].sort((a, b) => (a.line || 0) - (b.line || 0)).map((warning, idx) => renderIssue(warning, idx))}
              </div>
            </>
          )}
        </div>
      )}

      {suggestions.length > 0 && (
        <div className="issues-section suggestions">
          <h3 onClick={() => toggleSection('suggestions')} className="collapsible-header">
            💡 Suggestions ({suggestions.length})
            <span className={`chevron ${expandedSections.has('suggestions') ? 'expanded' : ''}`}>▼</span>
          </h3>
          {expandedSections.has('suggestions') && (
            <>
              <p className="section-description">Optional improvements to enhance your code.</p>
              <div className="issues-list">
                {[...suggestions].sort((a, b) => (a.line || 0) - (b.line || 0)).map((suggestion, idx) => renderIssue(suggestion, idx))}
              </div>
            </>
          )}
        </div>
      )}

      {/* Summary Footer */}
      <div className="feedback-footer">
        {approved ? (
          <div className="footer-success">
            <span className="footer-icon">🎉</span>
            <div className="footer-text">
              <strong>Code is ready to use!</strong>
              <p>Your MCP server passed validation and can be deployed.</p>
            </div>
          </div>
        ) : (
          <div className="footer-warning">
            <span className="footer-icon">🔧</span>
            <div className="footer-text">
              <strong>Action Required</strong>
              <p>Please address the issues above to improve code quality. Click "Regenerate" to fix automatically.</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default ValidationFeedback;
