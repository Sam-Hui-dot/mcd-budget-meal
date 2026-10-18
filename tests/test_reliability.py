"""Offline reliability regressions with synthetic inputs and isolated file trees."""
import copy
import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from test_budget_meal import NOW, FakeClient, demo, plan, reply
import quote_meals
from compare_meals import compare, markdown
from report_meals import html_report, restore_comparison


class ExportReliability(unittest.TestCase):
    def test_template_failure_keeps_valid_quote_and_json(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            with patch.object(quote_meals, 'PROJECT_ROOT', root), patch.object(quote_meals, 'html_report', side_effect=FileNotFoundError('PRIVATE-PATH')):
                client = FakeClient([reply()])
                _, result, stopped = quote_meals.run(plan(), client, root/'private/run', NOW)
            self.assertFalse(stopped)
            self.assertEqual(1, len(client.calls))
            self.assertEqual(2300, result['recommended'][0]['payable_cents'])
            self.assertIn('HTML报告未生成', markdown(result))
            self.assertNotIn('PRIVATE-PATH', markdown(result))
            saved = json.loads((root/'private/run/comparison.json').read_text(encoding='utf-8'))
            self.assertTrue(saved['warnings'])

    def test_html_write_failure_does_not_stop_or_hide_quotes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            original = Path.write_text
            def limited(path, *args, **kwargs):
                if path.name == 'meal-report.html':
                    raise PermissionError('PRIVATE-DETAILS')
                return original(path, *args, **kwargs)
            with patch.object(quote_meals, 'PROJECT_ROOT', root), patch.object(Path, 'write_text', limited):
                _, result, stopped = quote_meals.run(plan(), FakeClient([reply()]), root/'private/run', NOW)
            self.assertFalse(stopped)
            self.assertEqual(2300, result['recommended'][0]['payable_cents'])
            self.assertIn('HTML报告未生成', result['warnings'][0])

    def test_json_write_failure_keeps_report_and_terminal_result(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            original = Path.write_text
            def limited(path, *args, **kwargs):
                if path.name == 'comparison.json':
                    raise PermissionError('PRIVATE-DETAILS')
                return original(path, *args, **kwargs)
            with patch.object(quote_meals, 'PROJECT_ROOT', root), patch.object(Path, 'write_text', limited):
                _, result, stopped = quote_meals.run(plan(), FakeClient([reply()]), root/'private/run', NOW)
            self.assertFalse(stopped)
            self.assertTrue((root/'private/run/meal-report.html').is_file())
            self.assertIn('比较JSON未保存', markdown(result))
            self.assertEqual(2300, result['recommended'][0]['payable_cents'])

    def test_export_failure_does_not_change_business_stop(self):
        value = plan()
        second = copy.deepcopy(value['candidates'][0]); second['id'] = 'second'
        value['candidates'].append(second)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            with patch.object(quote_meals, 'PROJECT_ROOT', root), patch.object(quote_meals, 'html_report', side_effect=OSError()):
                _, result, stopped = quote_meals.run(value, FakeClient([reply(), {'error': {'code': -1}}]), root/'private/run', NOW)
            self.assertTrue(stopped)
            self.assertEqual(1, len(result['recommended']))
            self.assertEqual(1, len(result['excluded']))


class HistoricalRestore(unittest.TestCase):
    def saved(self):
        value = demo(); value['data_kind'] = 'live'
        for candidate in value['candidates']:
            candidate['quote']['quoted_at'] = NOW.isoformat()
        return compare(value, now=NOW)

    def test_old_comparison_restores_original_times_and_marks_history(self):
        source = self.saved()
        result = restore_comparison(source, now=NOW + timedelta(days=30))
        self.assertEqual([2300,2850], [p['payable_cents'] for p in result['recommended']])
        self.assertEqual(source['recommended'][0]['quoted_at'], result['recommended'][0]['quoted_at'])
        data = json.loads(html_report(result, historical=True).split('<script id="mealReportData" type="application/json">')[1].split('</script>')[0])
        self.assertTrue(data['historical'])
        self.assertEqual('live', data['kind'])
        self.assertEqual('保存的历史比较结果', data['meals'][0]['variants'][0]['sourceNote'])

    def test_normal_live_comparison_still_rejects_old_quotes(self):
        value = demo(); value['data_kind']='live'
        self.assertEqual(0, compare(value, now=NOW+timedelta(days=30))['summary']['valid_distinct'])

    def test_negative_missing_and_future_values_rejected(self):
        for field, replacement in [('payable_cents',-1),('quoted_at','2099-01-01T00:00:00+00:00'),('items',[]),('id',None)]:
            source=self.saved(); source['recommended'][0][field]=replacement
            with self.assertRaises(ValueError):
                restore_comparison(source, now=NOW)

    def test_empty_results_do_not_become_quoted_meals(self):
        source=self.saved(); source['recommended']=[];source['over_budget']=[]
        with self.assertRaises(ValueError):restore_comparison(source,NOW)

    def test_incorrect_remainders_are_recomputed_and_private_fields_dropped(self):
        source=self.saved(); source['recommended'][0]['remaining_cents']=999999
        source['Authorization']='Bearer SECRET'
        source['excluded']=[{'reason':'SECRET'}]
        result=restore_comparison(source,NOW)
        self.assertEqual(700,result['recommended'][0]['remaining_cents'])
        self.assertNotIn('SECRET',html_report(result,historical=True))


if __name__=='__main__':unittest.main()
