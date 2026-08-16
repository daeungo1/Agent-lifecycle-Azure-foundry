from lifecycle_ops.naming import (
    agent_name,
    continuous_eval_name,
    continuous_rule_id,
    department_names,
    env_suffix,
    knowledge_path,
    toolbox_file,
    toolbox_name,
)


def test_names_are_derived_from_department_configuration() -> None:
    assert department_names() == (
        "development",
        "human-resources",
        "marketing",
    )
    assert agent_name("human-resources") == "human-resources-agent"
    assert env_suffix("human-resources") == "HUMAN_RESOURCES"
    assert knowledge_path("human-resources").as_posix() == "knowledge/human-resources"
    assert toolbox_name("human-resources") == "human-resources-knowledge-toolbox"
    assert (
        toolbox_file("human-resources").as_posix()
        == "deploy/toolboxes/human-resources.yaml"
    )
    assert continuous_eval_name("human-resources") == "continuous-eval-human-resources"
    assert continuous_rule_id("human-resources") == (
        "continuous-response-completed-human-resources"
    )
