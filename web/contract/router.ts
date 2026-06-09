import type { InferContractRouterInputs } from "@orpc/contract";
import * as adminAgent from "./console/admin-agent";
import * as agent from "./console/agent";
import * as agentBind from "./console/agent-bind";
import { appDeleteContract } from "./console/apps";
import * as assetLibrary from "./console/asset-library";
import { bindPartnerStackContract, invoicesContract } from "./console/billing";
import * as explore from "./console/explore";
import {
  changePreferredProviderTypeContract,
  modelProvidersModelsContract,
} from "./console/model-providers";
import {
  notificationContract,
  notificationDismissContract,
} from "./console/notification";
import {
  pluginCheckInstalledContract,
  pluginLatestVersionsContract,
} from "./console/plugins";
import { systemFeaturesContract } from "./console/system";
import * as trigger from "./console/trigger";
import * as trialApp from "./console/try-app";
import {
  collectionPluginsContract,
  collectionsContract,
  searchAdvancedContract,
} from "./marketplace";

export const marketplaceRouterContract = {
  collections: collectionsContract,
  collectionPlugins: collectionPluginsContract,
  searchAdvanced: searchAdvancedContract,
};

export type MarketPlaceInputs = InferContractRouterInputs<
  typeof marketplaceRouterContract
>;

export const consoleRouterContract = {
  systemFeatures: systemFeaturesContract,
  apps: {
    deleteApp: appDeleteContract,
  },
  assetLibrary: {
    list: assetLibrary.assetLibraryListContract,
    detail: assetLibrary.assetLibraryDetailContract,
    patch: assetLibrary.assetLibraryPatchContract,
    delete: assetLibrary.assetLibraryDeleteContract,
    createPrompt: assetLibrary.assetLibraryCreatePromptContract,
  },
  explore: {
    apps: explore.exploreAppsContract,
    appDetail: explore.exploreAppDetailContract,
    installedApps: explore.exploreInstalledAppsContract,
    uninstallInstalledApp: explore.exploreInstalledAppUninstallContract,
    updateInstalledApp: explore.exploreInstalledAppPinContract,
    appAccessMode: explore.exploreInstalledAppAccessModeContract,
    installedAppParameters: explore.exploreInstalledAppParametersContract,
    installedAppMeta: explore.exploreInstalledAppMetaContract,
    banners: explore.exploreBannersContract,
  },
  trialApps: {
    info: trialApp.trialAppInfoContract,
    datasets: trialApp.trialAppDatasetsContract,
    parameters: trialApp.trialAppParametersContract,
    workflows: trialApp.trialAppWorkflowsContract,
  },
  modelProviders: {
    models: modelProvidersModelsContract,
    changePreferredProviderType: changePreferredProviderTypeContract,
  },
  plugins: {
    checkInstalled: pluginCheckInstalledContract,
    latestVersions: pluginLatestVersionsContract,
  },
  billing: {
    invoices: invoicesContract,
    bindPartnerStack: bindPartnerStackContract,
  },
  notification: notificationContract,
  notificationDismiss: notificationDismissContract,
  triggers: {
    list: trigger.triggersContract,
    providerInfo: trigger.triggerProviderInfoContract,
    subscriptions: trigger.triggerSubscriptionsContract,
    subscriptionBuilderCreate: trigger.triggerSubscriptionBuilderCreateContract,
    subscriptionBuilderUpdate: trigger.triggerSubscriptionBuilderUpdateContract,
    subscriptionBuilderVerifyUpdate:
      trigger.triggerSubscriptionBuilderVerifyUpdateContract,
    subscriptionVerify: trigger.triggerSubscriptionVerifyContract,
    subscriptionBuild: trigger.triggerSubscriptionBuildContract,
    subscriptionDelete: trigger.triggerSubscriptionDeleteContract,
    subscriptionUpdate: trigger.triggerSubscriptionUpdateContract,
    subscriptionBuilderLogs: trigger.triggerSubscriptionBuilderLogsContract,
    oauthConfig: trigger.triggerOAuthConfigContract,
    oauthConfigure: trigger.triggerOAuthConfigureContract,
    oauthDelete: trigger.triggerOAuthDeleteContract,
    oauthInitiate: trigger.triggerOAuthInitiateContract,
  },
  agent: {
    dashboard: agent.agentDashboardContract,
    invitationsList: agent.agentInvitationsListContract,
    invitationsCreate: agent.agentInvitationsCreateContract,
    invitees: agent.agentInviteesContract,
    withdrawalsList: agent.agentWithdrawalsListContract,
    withdrawalsCreate: agent.agentWithdrawalsCreateContract,
    bindPreview: agentBind.agentBindPreviewContract,
    bindConfirm: agentBind.agentBindConfirmContract,
    rebindRequest: agentBind.agentRebindRequestContract,
  },
  adminAgent: {
    list: adminAgent.adminAgentListContract,
    detail: adminAgent.adminAgentDetailContract,
    create: adminAgent.adminAgentCreateContract,
    patch: adminAgent.adminAgentPatchContract,
    suspend: adminAgent.adminAgentSuspendContract,
    consumption: adminAgent.adminAgentConsumptionContract,
    rebateRecords: adminAgent.adminRebateRecordsContract,
    rebindList: adminAgent.adminRebindListContract,
    rebindApprove: adminAgent.adminRebindApproveContract,
    rebindReject: adminAgent.adminRebindRejectContract,
    withdrawalList: adminAgent.adminWithdrawalListContract,
    withdrawalPay: adminAgent.adminWithdrawalPayContract,
    withdrawalReject: adminAgent.adminWithdrawalRejectContract,
  },
};
