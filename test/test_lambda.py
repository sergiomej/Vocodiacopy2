from util.lambda_handler import LambdaHandler


def test_lambda_handler():
    response = LambdaHandler.lambda_handler("hello", "", "")
    print(response)