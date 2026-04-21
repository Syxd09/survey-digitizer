export interface SurveyResponse {
  qId: string;
  question: string;
  value: string;
  confidence: number;
  isAISourced?: boolean;
  options?: string[];
  suggestions?: { value: string; score: number }[];
  status?: 'OK' | 'LOW_CONFIDENCE' | 'NOT_DETECTED' | 'AUTO_LOW_CONFIDENCE';
}



export interface MergedSurvey {
  formId: string;
  responses: Record<string, string>;
  confidenceScores: Record<string, number>;
  timestamp: string;
}

export const QUESTION_MAP: Record<string, string> = {
  q1: "I feel disconnected from the world around me.",
  q2: "Even around people I know, I don’t feel that I really belong.",
  q3: "I feel so distant from people.",
  q4: "I have no sense of togetherness with my peers.",
  q5: "I don’t feel related to anyone.",
  q6: "I catch myself losing all sense of connectedness with society.",
  q7: "I feel that I can share my problems with no one.",
  q8: "I don’t feel I participate in what is going on around me.",
  q9: "But even among my friends, there is no sense of brother/sisterhood.",
  q10: "I don’t feel I share a similar background with others.",
  q11: "My friends and acquaintances are like my family.",
  q12: "I feel a sense of togetherness with people I know.",
  q13: "I feel connected to others.",
  q14: "I see myself as a listener and a participant in a group.",
  q15: "I feel like an outsider.",
  q16: "I feel understood by the people I know.",
  q17: "I am able to relate to my peers.",
  q18: "I am able to connect with other people.",
  q19: "I see myself as a people person.",
  q20: "I feel a sense of belonging with my community.",
  q21: "Additional Survey Question 21",
  q22: "Additional Survey Question 22",
  q23: "Additional Survey Question 23",
  q24: "Additional Survey Question 24",
  q25: "Additional Survey Question 25",
};

class FormatterService {
  
  /**
   * Generates a clean JSON object for the survey.
   */
  formatToJson(merged: MergedSurvey) {
    return JSON.stringify({
      formId: merged.formId,
      timestamp: merged.timestamp,
      responses: merged.responses
    }, null, 2);
  }

  /**
   * Generates a CSV row with header.
   */
  formatToCsv(merged: MergedSurvey) {
    const qIds = Object.keys(QUESTION_MAP).sort((a, b) => {
      const numA = parseInt(a.replace('q', ''));
      const numB = parseInt(b.replace('q', ''));
      return numA - numB;
    });

    const header = ['FormID', 'Timestamp', ...qIds].join(',');
    const row = [
      merged.formId,
      merged.timestamp,
      ...qIds.map(id => merged.responses[id] || '')
    ].join(',');

    return `${header}\n${row}`;
  }

  /**
   * Merges multiple page results into one survey response.
   */
  mergePages(formId: string, pageResults: { rows: any[] }[]): MergedSurvey {
    const responses: Record<string, string> = {};
    const confidenceScores: Record<string, number> = {};

    pageResults.forEach(page => {
      page.rows.forEach(row => {
        // Assume row.sno maps to Q number (e.g. 1 -> q1)
        const qId = `q${row.sno}`;
        responses[qId] = row.value;
        confidenceScores[qId] = row.confidence;
      });
    });

    return {
      formId,
      responses,
      confidenceScores,
      timestamp: new Date().toISOString()
    };
  }

  /**
   * Formats raw extraction rows for the Table UI.
   */
  getStructuredRows(rows: any[]): SurveyResponse[] {
    return rows.map(row => {
      const qId = `q${row.sno}`;
      return {
        qId,
        question: QUESTION_MAP[qId] || row.question || `Question ${row.sno}`,
        value: row.value,
        confidence: row.confidence,
        isAISourced: row.isAISourced,
        options: row.options,
        suggestions: row.suggestions || [],
        status: row.status || 'OK'
      };
    });
  }


}

export const formatterService = new FormatterService();
