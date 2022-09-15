#!/bin/bash

PYTHON=python3

. otagent.env

${PYTHON} -m driver.main --config ./driver/config/driver_config.yaml \
--aws-region $AWS_REGION \
--db-identifier $OTTERTUNE_DB_IDENTIFIER \
--db-username $OTTERTUNE_DB_USERNAME \
--db-password $OTTERTUNE_DB_PASSWORD \
--api-key $OTTERTUNE_API_KEY \
--db-key $OTTERTUNE_DB_KEY \
--organization-id $OTTERTUNE_ORG_ID \
--db-host $OTTERTUNE_DB_HOST \
--db-port $OTTERTUNE_DB_PORT \
--db-version $OTTERTUNE_DB_VERSION \
--db-type $OTTERTUNE_DB_TYPE


exit $?

