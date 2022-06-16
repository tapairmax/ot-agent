#!/bin/bash

. ../ot-agent.env

python -m driver.main --config ./driver/config/driver_config.yaml --aws-region $AWS_REGION --db-identifier $OTTERTUNE_DB_IDENTIFIER --db-username $OTTERTUNE_DB_USERNAME --db-password $OTTERTUNE_DB_PASSWORD --api-key $OTTERTUNE_API_KEY --db-key $OTTERTUNE_DB_KEY --organization-id $OTTERTUNE_ORG_ID

exit $?

