/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

export interface Region {
  x: number; // 0 to 1
  y: number; // 0 to 1
  width: number; // 0 to 1
  height: number; // 0 to 1
}

export interface QuestionTemplate {
  id: string;
  label: string;
  type: 'choice' | 'boolean' | 'text';
  options?: { label: string; value: any; region: Region }[];
  region?: Region; // For text fields
}

export interface FormTemplate {
  id: string;
  name: string;
  pages: {
    pageNumber: number;
    questions: QuestionTemplate[];
  }[];
}

// Example Template: Standard 25-Question Survey
export const standardSurveyTemplate: FormTemplate = {
  id: 'std-survey-25',
  name: 'Standard 25-Question Survey',
  pages: [
    {
      pageNumber: 1,
      questions: Array.from({ length: 25 }, (_, i) => ({
        id: `q${i + 1}`,
        label: `Question ${i + 1}`,
        type: 'choice',
        options: [1, 2, 3, 4, 5, 6].map((val, col) => ({
          label: val.toString(),
          value: val,
          region: {
            x: 0.2 + col * 0.12,
            y: 0.1 + i * 0.035,
            width: 0.08,
            height: 0.03
          }
        }))
      }))
    }
  ]
};

export function getTemplateById(id: string): FormTemplate | undefined {
  if (id === 'std-survey-25') return standardSurveyTemplate;
  return undefined;
}
