"""Scoring rules for the retrieval probe; no server, no model."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.eval_retrieval import score, summarize


def hits(*texts):
    return [{'text': text, 'score': 0.5 - index / 10} for index, text in enumerate(texts)]


def test_core_uses_first_matching_rank_and_complete_uses_top_k_union():
    case = {'facts': ['晨间', '18']}
    result = score(case, hits('无关内容', '晨间 18', '其他'))
    assert result['rank'] == 2
    assert result['core'] == {1: False, 3: True, 5: True}
    assert result['complete_at'] == 3      # 最小的 k 是 3，Complete@1 仍算失败
    assert result['top_score'] == 0.5


def test_complete_requires_every_fact_within_k():
    case = {'facts': ['甲', '乙']}
    result = score(case, hits('甲', '乙'))
    assert result['rank'] == 1
    assert result['complete_at'] == 3      # needs both inside the first 3
    assert result['core'][1] is True


def test_unanswerable_case_reports_only_the_best_score():
    result = score({'facts': []}, hits('别的文档', '再一段'))
    assert result['rank'] is None and result['complete_at'] is None
    assert result['core'] == {1: False, 3: False, 5: False}
    assert result['top_score'] == 0.5


def test_summary_separates_scored_and_unanswerable():
    rows = [
        {**score({'facts': ['18']}, hits('18 分钟')), 'facts': ['18']},
        {**score({'facts': []}, hits('无关')), 'facts': []},
    ]
    summary = summarize(rows)
    assert summary['scored'] == 1 and summary['unanswerable'] == 1
    assert summary['core@1'] == 1 and summary['complete@1'] == 1
    assert summary['unanswerable_top_scores'] == [0.5]
