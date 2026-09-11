from project_intel import main


def test_main_runs(capsys):
    main()
    captured = capsys.readouterr()
    assert "project-intel" in captured.out.lower()
